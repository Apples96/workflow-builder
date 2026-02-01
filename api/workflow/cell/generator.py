"""
Cell Code Generator

This module handles code generation for individual workflow cells.
Each cell gets its own self-contained Python code that can be executed
independently with a shared context.

Key Components:
    - CellCodeGenerator: Generates code for individual cells
    - Parallel code generation for cells in the same layer
    - Code validation and cleanup utilities

The generator produces code that:
    - Includes all necessary imports and ParadigmClient
    - Defines an `execute_cell(context)` function
    - Accepts inputs from context dict
    - Returns outputs as a dict for the next cell
"""

import asyncio
import logging
import re
from typing import Optional, Dict, Any, List, Tuple

from ..models import WorkflowCell, CellStatus
from ...clients import create_anthropic_client
from ...config import settings
from ..prompts.loader import PromptLoader

logger = logging.getLogger(__name__)


def load_cell_prompt() -> str:
    """
    Load the cell generation system prompt from markdown file.

    Returns:
        str: The cell generation system prompt content

    Raises:
        FileNotFoundError: If the cell prompt cannot be loaded
    """
    return PromptLoader.load("cell")


class CellCodeGenerator:
    """
    Generates Python code for individual workflow cells.

    Each generated cell is self-contained with its own ParadigmClient
    and implements the execute_cell function signature.

    Attributes:
        anthropic_client: Anthropic API client for Claude calls
    """

    def __init__(self, anthropic_client=None):
        """
        Initialize the cell code generator.

        Args:
            anthropic_client: Optional Anthropic client. If not provided,
                            creates one using the centralized factory.
        """
        self.anthropic_client = anthropic_client or create_anthropic_client()

    async def generate_cell_code(
        self,
        cell: WorkflowCell,
        available_context: Dict[str, str],
        workflow_description: str
    ) -> str:
        """
        Generate Python code for a single cell.

        Args:
            cell: The cell definition with inputs/outputs
            available_context: Schema of variables available from previous cells
            workflow_description: Original workflow description for context

        Returns:
            str: The complete Python code for this cell

        Raises:
            Exception: If code generation fails
        """
        logger.info("Generating code for cell: {} (step {})".format(
            cell.name, cell.step_number
        ))

        # Load the system prompt
        system_prompt = load_cell_prompt()
        if not system_prompt:
            raise Exception("Could not load cell generation prompt")

        # Build the user message with cell context
        user_message = self._build_user_message(
            cell, available_context, workflow_description
        )

        try:
            # Call Claude to generate the code
            # Use configured max tokens (reduced from 32000 to save costs)
            response = self.anthropic_client.messages.create(
                model=settings.anthropic_model,
                max_tokens=settings.anthropic_max_tokens_cell,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
                timeout=settings.anthropic_timeout
            )

            # Get the raw output
            raw_output = response.content[0].text
            logger.info("Raw cell output generated ({} chars)".format(len(raw_output)))
            logger.info("Raw cell output (first 500 chars):\n{}".format(raw_output[:500]))

            # Extract and clean up the code
            cleaned_code = self._extract_code(raw_output)
            logger.info("Cleaned code ({} chars)".format(len(cleaned_code)))
            logger.info("Cleaned code (first 500 chars):\n{}".format(cleaned_code[:500]))

            # Validate the code
            validation_result = self._validate_code(cleaned_code)
            if not validation_result["valid"]:
                logger.error("Code validation failed. Full cleaned code:\n{}".format(cleaned_code))
                raise Exception(
                    "Generated cell code is invalid: {}".format(
                        validation_result["error"]
                    )
                )

            logger.info("Cell code validated successfully")
            return cleaned_code

        except Exception as e:
            logger.error("Cell code generation failed: {}".format(str(e)))
            raise Exception(
                "Failed to generate code for cell '{}': {}".format(
                    cell.name, str(e)
                )
            )

    def _build_user_message(
        self,
        cell: WorkflowCell,
        available_context: Dict[str, str],
        workflow_description: str
    ) -> str:
        """
        Build the user message for the code generation request.

        Args:
            cell: The cell definition
            available_context: Variables available from previous cells
            workflow_description: Original workflow description

        Returns:
            str: Formatted user message
        """
        # Format available inputs
        inputs_desc = []
        for var_name in cell.inputs_required:
            type_desc = available_context.get(var_name, "Any")
            inputs_desc.append("  - {}: {}".format(var_name, type_desc))

        # Format required outputs
        outputs_desc = []
        for var_name in cell.outputs_produced:
            outputs_desc.append("  - {}".format(var_name))

        message = """
Generate Python code for this workflow cell:

WORKFLOW CONTEXT:
{workflow_description}

CELL INFORMATION:
- Cell Name: {cell_name}
- Cell Description: {cell_description}
- Step Number: {step_number}
- Paradigm Tools to Use: {tools}

AVAILABLE INPUTS (from context dict):
{inputs}

REQUIRED OUTPUTS (must be in returned dict):
{outputs}

Generate complete, self-contained Python code that:
1. Defines the ParadigmClient class with only the methods needed
2. Defines `async def execute_cell(context: Dict[str, Any]) -> Dict[str, Any]`
3. Accesses inputs via context["variable_name"]
4. Returns a dict with all required outputs
5. Uses .format() for string interpolation (NOT f-strings)
6. Prints progress with print("CELL_OUTPUT: message")
""".format(
            workflow_description=workflow_description,
            cell_name=cell.name,
            cell_description=cell.description,
            step_number=cell.step_number,
            tools=", ".join(cell.paradigm_tools_used) if cell.paradigm_tools_used else "none",
            inputs="\n".join(inputs_desc) if inputs_desc else "  (none)",
            outputs="\n".join(outputs_desc) if outputs_desc else "  (none)"
        )

        return message

    def _extract_code(self, raw_output: str) -> str:
        """
        Extract Python code from Claude's output.

        The prompt asks for pure code, but we handle cases where:
        - Code is wrapped in markdown code blocks
        - There's explanatory text before/after the code

        Args:
            raw_output: Raw text from Claude

        Returns:
            str: Cleaned Python code
        """
        cleaned = raw_output.strip()

        # Strategy 1: Extract from markdown code blocks if present
        if "```python" in cleaned:
            blocks = re.findall(r'```python\s*(.*?)```', cleaned, re.DOTALL)
            if blocks:
                # Find the block with execute_cell, or use the largest one
                for block in blocks:
                    if "async def execute_cell" in block or "def execute_cell" in block:
                        cleaned = block.strip()
                        break
                else:
                    # No execute_cell found, use the largest block
                    cleaned = max(blocks, key=len).strip()
            else:
                # Unclosed code block - extract everything after ```python
                parts = cleaned.split("```python", 1)
                if len(parts) > 1:
                    code_part = parts[1]
                    if "```" in code_part:
                        cleaned = code_part.split("```")[0].strip()
                    else:
                        cleaned = code_part.strip()
        elif "```" in cleaned:
            # Generic code block without language specifier
            parts = cleaned.split("```")
            if len(parts) >= 2:
                # Find the part with execute_cell
                for i, part in enumerate(parts):
                    if i % 2 == 1 and ("async def execute_cell" in part or "def execute_cell" in part):
                        cleaned = part.strip()
                        break
                else:
                    # Use the largest odd-indexed part (inside code blocks)
                    code_parts = [parts[i] for i in range(1, len(parts), 2)]
                    if code_parts:
                        cleaned = max(code_parts, key=len).strip()

        # Strategy 2: Find code by looking for imports if output starts with text
        if not cleaned.startswith("import") and not cleaned.startswith("from") and not cleaned.startswith("#"):
            import_match = re.search(r'^(import |from )', cleaned, re.MULTILINE)
            if import_match:
                cleaned = cleaned[import_match.start():].strip()

        # Ensure execute_cell is async
        if "def execute_cell(" in cleaned and "async def execute_cell(" not in cleaned:
            cleaned = cleaned.replace("def execute_cell(", "async def execute_cell(")

        return cleaned

    def _validate_code(self, code: str) -> Dict[str, Any]:
        """
        Validate that the generated cell code is syntactically correct.

        Args:
            code: The code to validate

        Returns:
            dict: {"valid": bool, "error": str or None}
        """
        try:
            # Check for syntax errors
            compile(code, '<cell>', 'exec')

            # Check for required function
            if 'def execute_cell(' not in code:
                return {
                    "valid": False,
                    "error": "Missing execute_cell function"
                }

            # Check for async definition
            if 'async def execute_cell(' not in code:
                return {
                    "valid": False,
                    "error": "execute_cell must be async"
                }

            # Check for required imports
            if 'import asyncio' not in code:
                return {
                    "valid": False,
                    "error": "Missing asyncio import"
                }

            return {"valid": True, "error": None}

        except SyntaxError as e:
            return {
                "valid": False,
                "error": "Syntax error at line {}: {}".format(e.lineno, str(e))
            }
        except Exception as e:
            return {
                "valid": False,
                "error": "Validation error: {}".format(str(e))
            }


    async def generate_layer_cells_parallel(
        self,
        cells: List[WorkflowCell],
        available_context: Dict[str, str],
        workflow_description: str
    ) -> List[Tuple[WorkflowCell, str, Optional[Exception]]]:
        """
        Generate code for all cells in a layer concurrently.

        This method generates code for multiple cells in parallel, which is
        useful when all cells in a layer are independent and can be generated
        simultaneously.

        Args:
            cells: List of cells to generate code for (all in same layer)
            available_context: Schema of variables available from previous cells
            workflow_description: Original workflow description for context

        Returns:
            List of tuples: (cell, code, error)
            - cell: The WorkflowCell object
            - code: Generated code (or empty if error)
            - error: Exception if generation failed, None if successful
        """
        if not cells:
            return []

        layer = cells[0].layer if cells else 0
        logger.info("Generating code for {} cells in layer {} in parallel".format(
            len(cells), layer
        ))

        async def generate_single_cell(cell: WorkflowCell) -> Tuple[WorkflowCell, str, Optional[Exception]]:
            """Generate code for a single cell, capturing any errors."""
            try:
                code = await self.generate_cell_code(
                    cell=cell,
                    available_context=available_context,
                    workflow_description=workflow_description
                )
                return (cell, code, None)
            except Exception as e:
                logger.error("Failed to generate code for cell '{}': {}".format(
                    cell.name, str(e)
                ))
                return (cell, "", e)

        # Generate all cells in parallel
        tasks = [generate_single_cell(cell) for cell in cells]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        # Count successes and failures
        successes = sum(1 for _, _, err in results if err is None)
        failures = sum(1 for _, _, err in results if err is not None)

        logger.info("Layer {} code generation complete: {} successes, {} failures".format(
            layer, successes, failures
        ))

        return results


# Global generator instance
cell_generator = CellCodeGenerator()
