"""Cell code generation for individual workflow cells."""

import asyncio
import logging
import re
from typing import Optional, Dict, Any, List, Tuple

from ..models import WorkflowCell
from ...clients import create_anthropic_client
from ...config import settings
from ..prompts.loader import PromptLoader

logger = logging.getLogger(__name__)


def load_cell_prompt() -> str:
    """Load the cell generation system prompt from markdown file."""
    return PromptLoader.load("cell")


class CellCodeGenerator:
    """Generates self-contained Python code for individual workflow cells."""

    def __init__(self, anthropic_client=None):
        self.anthropic_client = anthropic_client or create_anthropic_client()

    async def generate_cell_code(
        self,
        cell: WorkflowCell,
        available_context: Dict[str, str],
        workflow_description: str,
        producer_return_hints: Optional[Dict[str, str]] = None,
        available_tools=None
    ) -> str:
        """Generate Python code for a single cell. Retries once on validation failure.

        Args:
            cell: The cell to generate code for
            available_context: Variable name → type description
            workflow_description: The full workflow description
            producer_return_hints: Hints from upstream cells about output formats
            available_tools: AgentDiscoveryResponse with discovered tools (optional)
        """
        logger.info("Generating code for cell: {} (step {})".format(
            cell.name, cell.step_number
        ))

        system_prompt = load_cell_prompt()
        if not system_prompt:
            raise Exception("Could not load cell generation prompt")

        user_message = self._build_user_message(
            cell, available_context, workflow_description,
            producer_return_hints=producer_return_hints,
            available_tools=available_tools
        )

        last_error = None
        max_gen_attempts = 2

        for attempt in range(1, max_gen_attempts + 1):
            try:
                messages = [{"role": "user", "content": user_message}]

                # On retry, append the validation error as feedback
                if last_error and attempt > 1:
                    logger.info("Retrying code generation (attempt {}/{}) after error: {}".format(
                        attempt, max_gen_attempts, last_error))
                    messages.append({"role": "assistant", "content": "```python\n# (previous attempt had an error)\n```"})
                    messages.append({"role": "user", "content": (
                        "Your previous code generation attempt failed validation: {}\n\n"
                        "Please generate the code again. Output ONLY valid Python code — "
                        "no markdown, no explanations, no text before or after the code. "
                        "The code must start with import statements."
                    ).format(last_error)})

                response = self.anthropic_client.messages.create(
                    model=settings.anthropic_model,
                    max_tokens=settings.anthropic_max_tokens_cell,
                    system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
                    messages=messages,
                    timeout=settings.anthropic_timeout
                )

                raw_output = response.content[0].text
                logger.info("Raw cell output generated ({} chars, attempt {})".format(
                    len(raw_output), attempt))
                logger.info("Raw cell output (first 500 chars):\n{}".format(raw_output[:500]))

                cleaned_code = self._extract_code(raw_output)
                logger.info("Cleaned code ({} chars)".format(len(cleaned_code)))
                logger.info("Cleaned code (first 500 chars):\n{}".format(cleaned_code[:500]))

                validation_result = self._validate_code(cleaned_code)
                if not validation_result["valid"]:
                    last_error = validation_result["error"]
                    logger.warning("Code validation failed (attempt {}): {}".format(
                        attempt, last_error))
                    if attempt < max_gen_attempts:
                        continue
                    # Final attempt failed — raise
                    logger.error("Code validation failed after {} attempts. Full cleaned code:\n{}".format(
                        max_gen_attempts, cleaned_code))
                    raise Exception(
                        "Generated cell code is invalid: {}".format(last_error)
                    )

                logger.info("Cell code validated successfully (attempt {})".format(attempt))
                return cleaned_code

            except Exception as e:
                error_str = str(e)
                # If this is a validation error and we can retry, continue
                if "Generated cell code is invalid" in error_str and attempt < max_gen_attempts:
                    last_error = error_str
                    continue
                logger.error("Cell code generation failed: {}".format(error_str))
                raise Exception(
                    "Failed to generate code for cell '{}': {}".format(
                        cell.name, error_str
                    )
                )

    def _build_user_message(
        self,
        cell: WorkflowCell,
        available_context: Dict[str, str],
        workflow_description: str,
        producer_return_hints: Optional[Dict[str, str]] = None,
        available_tools=None
    ) -> str:
        """Build the user message for the code generation request."""
        inputs_desc = []
        for var_name in cell.inputs_required:
            type_desc = available_context.get(var_name, "Any")
            hint = ""
            if producer_return_hints and var_name in producer_return_hints:
                hint = "\n    ACTUAL FORMAT from producer cell: {}".format(
                    producer_return_hints[var_name]
                )
            inputs_desc.append("  - {}: {}{}".format(var_name, type_desc, hint))

        outputs_desc = []
        for var_name in cell.outputs_produced:
            type_desc = available_context.get(var_name, "Any")
            outputs_desc.append("  - {}: {}".format(var_name, type_desc))

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
1. Defines `async def execute_cell(context: Dict[str, Any]) -> Dict[str, Any]`
2. Does NOT define ParadigmClient (it is pre-injected, just instantiate it)
3. Accesses inputs via context["variable_name"]
4. Returns a dict with all required outputs
5. NEVER uses f-strings. Uses .format() for print/log messages. Uses concatenation (+) when building strings that include context variables from previous cells (they may contain {{ }} that break .format())
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

        # Append MCP tool documentation if this cell uses MCP tools
        if available_tools:
            mcp_tools = getattr(available_tools, 'mcp_tools', [])
            if mcp_tools:
                mcp_section = self._build_mcp_tools_section(cell, mcp_tools)
                if mcp_section:
                    message += mcp_section

        return message

    def _build_mcp_tools_section(self, cell: WorkflowCell, mcp_tools) -> str:
        """Build MCP tool documentation section for the user message.

        Only includes MCP tool info if the cell references MCP tools.
        """
        # Build list of available MCP tool names for reference
        mcp_names = []
        for tool in mcp_tools:
            name = getattr(tool, 'name', '') if hasattr(tool, 'name') else tool.get('name', '')
            desc = getattr(tool, 'description', '') if hasattr(tool, 'description') else tool.get('description', '')
            mcp_names.append((name, desc))

        if not mcp_names:
            return ""

        lines = [
            "",
            "MCP TOOLS AVAILABLE (called via agent_query):",
            "The following MCP tools are configured on the Paradigm agent.",
            "They are invoked automatically when you call agent_query with a relevant query.",
        ]
        for name, desc in mcp_names:
            lines.append("- {}: {}".format(name, desc or "MCP tool"))
        lines.append("")

        return "\n".join(lines)

    def _extract_code(self, raw_output: str) -> str:
        """Extract Python code from Claude's raw output, handling markdown blocks and text."""
        cleaned = raw_output.strip()

        # Extract from markdown code blocks if present
        if "```python" in cleaned:
            blocks = re.findall(r'```python\s*(.*?)```', cleaned, re.DOTALL)
            if blocks:
                # Find the block with execute_cell, or use the largest one
                for block in blocks:
                    if "async def execute_cell" in block or "def execute_cell" in block:
                        cleaned = block.strip()
                        break
                else:
                    cleaned = max(blocks, key=len).strip()
            else:
                # Unclosed code block
                parts = cleaned.split("```python", 1)
                if len(parts) > 1:
                    code_part = parts[1]
                    if "```" in code_part:
                        cleaned = code_part.split("```")[0].strip()
                    else:
                        cleaned = code_part.strip()
        elif "```" in cleaned:
            parts = cleaned.split("```")
            if len(parts) >= 2:
                # Find the part with execute_cell
                for i, part in enumerate(parts):
                    if i % 2 == 1 and ("async def execute_cell" in part or "def execute_cell" in part):
                        cleaned = part.strip()
                        break
                else:
                    code_parts = [parts[i] for i in range(1, len(parts), 2)]
                    if code_parts:
                        cleaned = max(code_parts, key=len).strip()

        # Find code by looking for imports if output starts with text
        if not cleaned.startswith("import") and not cleaned.startswith("from") and not cleaned.startswith("#"):
            import_match = re.search(r'^(import |from )', cleaned, re.MULTILINE)
            if import_match:
                cleaned = cleaned[import_match.start():].strip()

        # Ensure execute_cell is async
        if "def execute_cell(" in cleaned and "async def execute_cell(" not in cleaned:
            cleaned = cleaned.replace("def execute_cell(", "async def execute_cell(")

        return cleaned

    def _validate_code(self, code: str) -> Dict[str, Any]:
        """Validate that the generated cell code is syntactically correct."""
        try:
            compile(code, '<cell>', 'exec')

            if 'def execute_cell(' not in code:
                return {
                    "valid": False,
                    "error": "Missing execute_cell function"
                }

            if 'async def execute_cell(' not in code:
                return {
                    "valid": False,
                    "error": "execute_cell must be async"
                }

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
        workflow_description: str,
        producer_return_hints: Optional[Dict[str, str]] = None
    ) -> List[Tuple[WorkflowCell, str, Optional[Exception]]]:
        """Generate code for all cells in a layer concurrently."""
        if not cells:
            return []

        layer = cells[0].layer if cells else 0
        logger.info("Generating code for {} cells in layer {} in parallel".format(
            len(cells), layer
        ))

        async def generate_single_cell(cell: WorkflowCell) -> Tuple[WorkflowCell, str, Optional[Exception]]:
            try:
                code = await self.generate_cell_code(
                    cell=cell,
                    available_context=available_context,
                    workflow_description=workflow_description,
                    producer_return_hints=producer_return_hints
                )
                return (cell, code, None)
            except Exception as e:
                logger.error("Failed to generate code for cell '{}': {}".format(
                    cell.name, str(e)
                ))
                return (cell, "", e)

        tasks = [generate_single_cell(cell) for cell in cells]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        successes = sum(1 for _, _, err in results if err is None)
        failures = sum(1 for _, _, err in results if err is not None)

        logger.info("Layer {} code generation complete: {} successes, {} failures".format(
            layer, successes, failures
        ))

        return results


# Global generator instance
cell_generator = CellCodeGenerator()
