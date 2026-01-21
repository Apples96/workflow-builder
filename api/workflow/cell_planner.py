"""
Cell-Based Workflow Planner

This module handles the planning phase of cell-based workflow execution.
It breaks down user workflow descriptions into discrete, sequential cells
that can be generated and executed one at a time.

Key Components:
    - WorkflowPlanner: Creates workflow plans from natural language descriptions
    - Plan validation and cell dependency resolution

The planner uses Claude to analyze the user's description and produce
a structured plan with:
    - Ordered list of cells
    - Input/output dependencies between cells
    - Paradigm API tools needed per cell
    - Shared context schema for data flow
"""

import json
import logging
import re
from pathlib import Path
from typing import Optional, Dict, Any, List

from anthropic import Anthropic
from .models import WorkflowPlan, WorkflowCell, CellStatus
from ..config import settings

logger = logging.getLogger(__name__)


def load_planner_prompt() -> str:
    """
    Load the workflow planner system prompt from markdown file.

    Returns:
        str: The planner system prompt content, or empty string if not found
    """
    try:
        current_dir = Path(__file__).parent
        prompt_file = current_dir / "planner_prompt.md"

        if prompt_file.exists():
            with open(prompt_file, 'r', encoding='utf-8') as f:
                content = f.read()
            logger.info("Loaded planner system prompt from {}".format(prompt_file))
            return content
        else:
            logger.warning("Planner system prompt not found at {}".format(prompt_file))
            return ""
    except Exception as e:
        logger.error("Error loading planner system prompt: {}".format(e))
        return ""


class WorkflowPlanner:
    """
    Creates workflow plans from natural language descriptions.

    The planner analyzes user descriptions and breaks them into discrete
    cells that can be executed sequentially. Each cell represents one
    logical step in the workflow.

    Attributes:
        anthropic_client: Anthropic API client for Claude calls
    """

    def __init__(self, anthropic_client: Optional[Anthropic] = None):
        """
        Initialize the workflow planner.

        Args:
            anthropic_client: Optional Anthropic client. If not provided,
                            creates one using settings.
        """
        self.anthropic_client = anthropic_client or Anthropic(
            api_key=settings.anthropic_api_key
        )

    async def create_plan(
        self,
        description: str,
        context: Optional[Dict[str, Any]] = None
    ) -> WorkflowPlan:
        """
        Create a workflow plan from a natural language description.

        Analyzes the description and produces a structured plan with
        ordered cells, dependencies, and data flow schema.

        Args:
            description: Natural language description of the workflow
            context: Optional additional context (e.g., attached file IDs)

        Returns:
            WorkflowPlan: Complete plan with cell definitions

        Raises:
            Exception: If planning fails or produces invalid output
        """
        logger.info("Creating workflow plan for: {}...".format(description[:100]))

        # Load the system prompt
        system_prompt = load_planner_prompt()
        if not system_prompt:
            raise Exception("Could not load planner system prompt")

        # Build the user message with context
        user_message = self._build_user_message(description, context)

        try:
            # Call Claude to generate the plan
            response = self.anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=8000,  # Increased to handle complex workflows
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}]
            )

            # Parse the response
            raw_output = response.content[0].text
            logger.info("Raw planner output: {}".format(raw_output[:500]))

            # Parse JSON from response
            plan_data = self._parse_plan_output(raw_output)

            # Create the WorkflowPlan
            plan = self._create_plan_from_data(plan_data, description)

            logger.info("Created plan with {} cells".format(len(plan.cells)))
            return plan

        except Exception as e:
            logger.error("Planning failed: {}".format(str(e)))
            raise Exception("Failed to create workflow plan: {}".format(str(e)))

    def _build_user_message(
        self,
        description: str,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Build the user message for the planning request.

        Args:
            description: The workflow description
            context: Optional additional context

        Returns:
            str: Formatted user message
        """
        message_parts = [
            "Create a workflow plan for the following description:",
            "",
            "WORKFLOW DESCRIPTION:",
            description,
            ""
        ]

        # Add context information if provided
        if context:
            message_parts.append("ADDITIONAL CONTEXT:")
            if context.get("uploaded_file_ids"):
                message_parts.append(
                    "- User has attached files with IDs: {}".format(
                        context["uploaded_file_ids"]
                    )
                )
                message_parts.append(
                    "- These are available as 'attached_file_ids' in the first cell"
                )
            if context.get("use_uploaded_files"):
                message_parts.append(
                    "- The workflow should use the attached files"
                )
            message_parts.append("")

        message_parts.append(
            "Generate a JSON plan with discrete cells for this workflow."
        )

        return "\n".join(message_parts)

    def _parse_plan_output(self, raw_output: str) -> Dict[str, Any]:
        """
        Parse the JSON plan from Claude's output.

        Handles potential markdown formatting and extracts clean JSON.

        Args:
            raw_output: Raw text output from Claude

        Returns:
            dict: Parsed plan data

        Raises:
            Exception: If JSON parsing fails
        """
        # Clean up the output - remove markdown if present
        cleaned = raw_output.strip()

        # Remove markdown code blocks if present
        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[1].split("```")[0]
        elif "```" in cleaned:
            cleaned = cleaned.split("```")[1].split("```")[0]

        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            error_line = e.lineno if hasattr(e, 'lineno') else None
            error_col = e.colno if hasattr(e, 'colno') else None
            error_pos = e.pos if hasattr(e, 'pos') else None

            logger.error("Failed to parse plan JSON: {}".format(e))
            logger.error("Error at line {}, column {}, position {}".format(error_line, error_col, error_pos))

            # Log the area around the error for debugging
            if error_pos:
                start = max(0, error_pos - 200)
                end = min(len(cleaned), error_pos + 200)
                context = cleaned[start:end]
                logger.error("Context around error: ...{}...".format(context))

            # Log full output to a file for inspection
            try:
                import tempfile
                with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                    f.write(raw_output)
                    logger.error("Full output saved to: {}".format(f.name))
            except:
                logger.error("Full raw output (first 2000 chars): {}".format(raw_output[:2000]))

            # Try to fix common JSON issues
            fixed_json = self._try_fix_json(cleaned)
            if fixed_json:
                try:
                    result = json.loads(fixed_json)
                    logger.info("Successfully parsed JSON after auto-fix")
                    return result
                except json.JSONDecodeError:
                    logger.error("Auto-fix failed")

            # Try to extract JSON with regex as fallback
            json_match = re.search(r'\{[\s\S]*\}', raw_output)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass

            raise Exception("Failed to parse workflow plan: {}".format(str(e)))

    def _try_fix_json(self, json_str: str) -> Optional[str]:
        """
        Attempt to fix common JSON formatting issues.

        Args:
            json_str: The malformed JSON string

        Returns:
            str: Fixed JSON string, or None if unfixable
        """
        try:
            # Fix common issues:
            # 1. Trailing commas before closing braces/brackets
            fixed = re.sub(r',(\s*[}\]])', r'\1', json_str)

            # 2. Missing commas between objects in arrays
            # (This is harder to fix reliably, skip for now)

            # 3. Unescaped quotes in strings (very hard to fix reliably)
            # Skip this as it's too risky

            return fixed
        except Exception as e:
            logger.error("JSON auto-fix error: {}".format(e))
            return None

    def _create_plan_from_data(
        self,
        plan_data: Dict[str, Any],
        description: str
    ) -> WorkflowPlan:
        """
        Create a WorkflowPlan object from parsed data.

        Args:
            plan_data: Parsed JSON plan data
            description: Original workflow description

        Returns:
            WorkflowPlan: Fully constructed plan object
        """
        plan = WorkflowPlan(
            description=description,
            shared_context_schema=plan_data.get("shared_context_schema", {}),
            status="ready"
        )

        # Create cells from plan data
        cells_data = plan_data.get("cells", [])
        for cell_data in cells_data:
            cell = WorkflowCell(
                workflow_id=plan.workflow_id,
                step_number=cell_data.get("step_number", 0),
                name=cell_data.get("name", "Unnamed Step"),
                description=cell_data.get("description", ""),
                inputs_required=cell_data.get("inputs_required", []),
                outputs_produced=cell_data.get("outputs_produced", []),
                paradigm_tools_used=cell_data.get("paradigm_tools_used", []),
                status=CellStatus.PENDING
            )
            plan.cells.append(cell)

        # Validate the plan
        self._validate_plan(plan)

        return plan

    def _validate_plan(self, plan: WorkflowPlan) -> None:
        """
        Validate that the plan is coherent and executable.

        Checks:
        - At least one cell exists
        - Final cell produces 'final_result'
        - Dependencies are satisfiable

        Args:
            plan: The plan to validate

        Raises:
            Exception: If validation fails
        """
        if not plan.cells:
            raise Exception("Plan must have at least one cell")

        # Check that the last cell produces final_result
        last_cell = plan.cells[-1]
        if "final_result" not in last_cell.outputs_produced:
            logger.warning(
                "Last cell '{}' does not produce 'final_result', adding it".format(
                    last_cell.name
                )
            )
            last_cell.outputs_produced.append("final_result")

        # Check dependency chain
        available_vars = {"user_input", "attached_file_ids"}
        for cell in plan.cells:
            # Check that all required inputs are available
            missing = set(cell.inputs_required) - available_vars
            if missing:
                logger.warning(
                    "Cell '{}' requires unavailable inputs: {}".format(
                        cell.name, missing
                    )
                )

            # Add this cell's outputs to available vars
            available_vars.update(cell.outputs_produced)

        logger.info("Plan validation passed")


# Global planner instance
workflow_planner = WorkflowPlanner()
