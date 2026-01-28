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
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

from anthropic import Anthropic
from .models import WorkflowCell, CellStatus
from ..config import settings

logger = logging.getLogger(__name__)


def load_cell_prompt() -> str:
    """
    Load the cell generation system prompt from markdown file.

    Returns:
        str: The cell generation system prompt content, or empty string if not found
    """
    try:
        current_dir = Path(__file__).parent
        prompt_file = current_dir / "cell_prompt.md"

        if prompt_file.exists():
            with open(prompt_file, 'r', encoding='utf-8') as f:
                content = f.read()
            logger.info("Loaded cell generation prompt from {}".format(prompt_file))
            return content
        else:
            logger.warning("Cell generation prompt not found at {}".format(prompt_file))
            return ""
    except Exception as e:
        logger.error("Error loading cell generation prompt: {}".format(e))
        return ""


class CellCodeGenerator:
    """
    Generates Python code for individual workflow cells.

    Each generated cell is self-contained with its own ParadigmClient
    and implements the execute_cell function signature.

    Attributes:
        anthropic_client: Anthropic API client for Claude calls
    """

    def __init__(self, anthropic_client: Optional[Anthropic] = None):
        """
        Initialize the cell code generator.

        Args:
            anthropic_client: Optional Anthropic client. If not provided,
                            creates one using settings.
        """
        self.anthropic_client = anthropic_client or Anthropic(
            api_key=settings.anthropic_api_key
        )

    async def generate_cell_code(
        self,
        cell: WorkflowCell,
        available_context: Dict[str, str],
        workflow_description: str
    ) -> tuple[str, str]:
        """
        Generate Python code and description for a single cell.

        Args:
            cell: The cell definition with inputs/outputs
            available_context: Schema of variables available from previous cells
            workflow_description: Original workflow description for context

        Returns:
            tuple: (description, code) - Description explaining what the cell does
                   in plain English, and the complete Python code for this cell

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
            response = self.anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=8000,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}]
            )

            # Get the raw output
            raw_output = response.content[0].text
            logger.info("Raw cell output generated ({} chars)".format(len(raw_output)))
            # Debug: log the start of raw output to verify DESCRIPTION/CODE format
            logger.info("Raw cell output (first 1000 chars):\n{}".format(raw_output[:1000]))

            # Parse description and code
            description, code = self._parse_output(raw_output)

            # Clean up the code
            cleaned_code = self._clean_code(code)

            # Validate the code
            validation_result = self._validate_code(cleaned_code)
            if not validation_result["valid"]:
                raise Exception(
                    "Generated cell code is invalid: {}".format(
                        validation_result["error"]
                    )
                )

            logger.info("Cell code validated successfully")
            return (description, cleaned_code)

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

    def _parse_output(self, raw_output: str) -> tuple[str, str]:
        """
        Parse Claude's output to extract description and code.

        Expected format:
        DESCRIPTION:
        [description text]

        CODE:
        [python code]

        Args:
            raw_output: Raw text from Claude

        Returns:
            tuple: (description, code)

        Raises:
            Exception: If parsing fails
        """
        try:
            # Look for DESCRIPTION: and CODE: markers
            if "DESCRIPTION:" in raw_output and "CODE:" in raw_output:
                # Split by markers
                parts = raw_output.split("CODE:")
                desc_section = parts[0]
                code_section = parts[1] if len(parts) > 1 else ""

                # Extract description
                description = desc_section.split("DESCRIPTION:")[1].strip()

                # Extract code
                code = code_section.strip()

                logger.info("Parsed description ({} chars) and code ({} chars)".format(
                    len(description), len(code)
                ))

                return (description, code)
            else:
                # Fallback: if no markers found, try to split by code blocks
                logger.warning("DESCRIPTION/CODE markers not found, attempting fallback parsing")

                # Try to find code block
                if "```python" in raw_output:
                    parts = raw_output.split("```python")
                    description = parts[0].strip()
                    code = parts[1].split("```")[0].strip() if len(parts) > 1 else raw_output
                    return (description or "No description provided", code)
                else:
                    # Last resort: assume entire output is code
                    logger.warning("Could not parse description, using default")
                    return ("No description provided", raw_output)

        except Exception as e:
            logger.error("Failed to parse output: {}".format(e))
            # Return safe defaults
            return ("Error parsing description", raw_output)

    def _clean_code(self, code: str) -> str:
        """
        Clean up generated code by removing markdown and fixing common issues.

        Args:
            code: Raw code from Claude

        Returns:
            str: Cleaned code
        """
        cleaned = code.strip()

        # Remove markdown code blocks if present
        if "```python" in cleaned:
            cleaned = cleaned.split("```python")[1].split("```")[0]
        elif "```" in cleaned:
            parts = cleaned.split("```")
            if len(parts) >= 2:
                cleaned = parts[1].split("```")[0]

        cleaned = cleaned.strip()

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
    ) -> List[Tuple[WorkflowCell, str, str, Optional[Exception]]]:
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
            List of tuples: (cell, description, code, error)
            - cell: The WorkflowCell object
            - description: Generated code description (or empty if error)
            - code: Generated code (or empty if error)
            - error: Exception if generation failed, None if successful
        """
        if not cells:
            return []

        layer = cells[0].layer if cells else 0
        logger.info("Generating code for {} cells in layer {} in parallel".format(
            len(cells), layer
        ))

        async def generate_single_cell(cell: WorkflowCell) -> Tuple[WorkflowCell, str, str, Optional[Exception]]:
            """Generate code for a single cell, capturing any errors."""
            try:
                description, code = await self.generate_cell_code(
                    cell=cell,
                    available_context=available_context,
                    workflow_description=workflow_description
                )
                return (cell, description, code, None)
            except Exception as e:
                logger.error("Failed to generate code for cell '{}': {}".format(
                    cell.name, str(e)
                ))
                return (cell, "", "", e)

        # Generate all cells in parallel
        tasks = [generate_single_cell(cell) for cell in cells]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        # Count successes and failures
        successes = sum(1 for _, _, _, err in results if err is None)
        failures = sum(1 for _, _, _, err in results if err is not None)

        logger.info("Layer {} code generation complete: {} successes, {} failures".format(
            layer, successes, failures
        ))

        return results


# Global generator instance
cell_generator = CellCodeGenerator()
