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
from typing import Optional, Dict, Any, List, Tuple

from ..models import WorkflowPlan, WorkflowCell, CellStatus
from ...clients import create_anthropic_client
from ...config import settings
from ..prompts.loader import PromptLoader

logger = logging.getLogger(__name__)


def parse_layer_structure_from_description(description: str) -> Dict[str, Tuple[int, int]]:
    """
    Parse the layer structure from a layer-structured enhanced description.

    Extracts STEP X.Y patterns and maps them to (layer, sublayer_index) tuples.
    This allows us to validate and fix Claude's output if it doesn't preserve
    the parallel structure.

    Args:
        description: The enhanced workflow description with LAYER/STEP format

    Returns:
        Dict mapping step identifiers to (layer, sublayer_index) tuples.
        Example: {"1.1": (1, 1), "2.1": (2, 1), "2.2": (2, 2), "3.1": (3, 1)}
    """
    layer_structure = {}

    # Pattern to match "STEP X.Y:" where X is layer and Y is sublayer_index
    # This handles formats like "STEP 2.1:", "STEP 2.1 :", "STEP 2.1-"
    step_pattern = re.compile(r'STEP\s+(\d+)\.(\d+)\s*[:\-]', re.IGNORECASE)

    for match in step_pattern.finditer(description):
        layer = int(match.group(1))
        sublayer = int(match.group(2))
        step_id = "{}.{}".format(layer, sublayer)
        layer_structure[step_id] = (layer, sublayer)
        logger.debug("Parsed step {} -> layer={}, sublayer={}".format(step_id, layer, sublayer))

    if layer_structure:
        # Log summary of parallel layers
        layers = {}
        for step_id, (layer, sublayer) in layer_structure.items():
            if layer not in layers:
                layers[layer] = []
            layers[layer].append(step_id)

        parallel_layers = [l for l, steps in layers.items() if len(steps) > 1]
        if parallel_layers:
            logger.info("Detected parallel structure: {} total layers, parallel layers: {}".format(
                len(layers), parallel_layers
            ))
        else:
            logger.info("Detected sequential structure: {} layers, no parallelization".format(
                len(layers)
            ))

    return layer_structure


def load_planner_prompt() -> str:
    """
    Load the workflow planner system prompt from markdown file.

    Returns:
        str: The planner system prompt content

    Raises:
        FileNotFoundError: If the planner prompt cannot be loaded
    """
    return PromptLoader.load("planner")


class WorkflowPlanner:
    """
    Creates workflow plans from natural language descriptions.

    The planner analyzes user descriptions and breaks them into discrete
    cells that can be executed sequentially. Each cell represents one
    logical step in the workflow.

    Attributes:
        anthropic_client: Anthropic API client for Claude calls
    """

    def __init__(self, anthropic_client=None):
        """
        Initialize the workflow planner.

        Args:
            anthropic_client: Optional Anthropic client. If not provided,
                            creates one using the centralized factory.
        """
        self.anthropic_client = anthropic_client or create_anthropic_client()

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
            # Parse layer structure from the description BEFORE calling Claude
            # This allows us to validate and fix Claude's output if needed
            expected_layer_structure = parse_layer_structure_from_description(description)

            if expected_layer_structure:
                logger.info("Parsed expected layer structure with {} steps from description".format(
                    len(expected_layer_structure)
                ))
            else:
                logger.info("No STEP X.Y pattern found in description, using Claude's layer assignments")

            # Call Claude to generate the plan
            response = self.anthropic_client.messages.create(
                model=settings.anthropic_model,
                max_tokens=settings.anthropic_max_tokens_plan,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}]
            )

            # Parse the response
            raw_output = response.content[0].text
            logger.info("Raw planner output: {}".format(raw_output[:500]))

            # Parse JSON from response
            plan_data = self._parse_plan_output(raw_output)

            # Create the WorkflowPlan with expected layer structure for validation
            plan = self._create_plan_from_data(plan_data, description, expected_layer_structure)

            # Log parallelization info
            if plan.is_parallel_workflow():
                layers = plan.get_cells_by_layer()
                parallel_layers = [l for l, cells in layers.items() if len(cells) > 1]
                logger.info("Created PARALLEL plan with {} cells across {} layers (parallel: {})".format(
                    len(plan.cells), len(layers), parallel_layers
                ))
            else:
                logger.info("Created SEQUENTIAL plan with {} cells".format(len(plan.cells)))

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
        description: str,
        expected_layer_structure: Optional[Dict[str, Tuple[int, int]]] = None
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
                # Parallelization fields
                layer=cell_data.get("layer", 1),
                sublayer_index=cell_data.get("sublayer_index", 1),
                depends_on=cell_data.get("depends_on", []),
                # Data flow fields
                inputs_required=cell_data.get("inputs_required", []),
                outputs_produced=cell_data.get("outputs_produced", []),
                paradigm_tools_used=cell_data.get("paradigm_tools_used", []),
                status=CellStatus.PENDING
            )
            plan.cells.append(cell)

        # Fix layer structure if expected structure is provided
        # This corrects Claude's output if it didn't preserve parallel layers
        if expected_layer_structure:
            self._fix_layer_structure(plan, expected_layer_structure)

        # Validate the plan
        self._validate_plan(plan)

        return plan

    def _fix_layer_structure(
        self,
        plan: WorkflowPlan,
        expected_structure: Dict[str, Tuple[int, int]]
    ) -> None:
        """
        Fix the layer structure of a plan based on expected structure from description.

        If Claude output cells with incorrect layer assignments (e.g., sequential layers
        instead of parallel), this method fixes them based on the parsed STEP X.Y format
        from the enhanced description.

        Args:
            plan: The plan to fix
            expected_structure: Dict mapping step IDs like "2.1" to (layer, sublayer_index)
        """
        if not expected_structure:
            logger.info("No expected structure provided, skipping layer fix")
            return

        # Build a mapping from cell order to expected structure
        # The assumption is cells are created in the order they appear in the description
        sorted_steps = sorted(expected_structure.keys(), key=lambda s: (
            int(s.split('.')[0]),  # Primary sort by layer
            int(s.split('.')[1])   # Secondary sort by sublayer
        ))

        if len(plan.cells) != len(sorted_steps):
            logger.warning(
                "Cell count ({}) doesn't match expected step count ({}), attempting best-effort fix".format(
                    len(plan.cells), len(sorted_steps)
                )
            )

        # Track if any fixes were made
        fixes_made = 0

        # Try to match cells to expected structure
        for i, cell in enumerate(plan.cells):
            if i < len(sorted_steps):
                step_id = sorted_steps[i]
                expected_layer, expected_sublayer = expected_structure[step_id]

                if cell.layer != expected_layer or cell.sublayer_index != expected_sublayer:
                    logger.info(
                        "Fixing cell '{}': layer {} -> {}, sublayer {} -> {}".format(
                            cell.name,
                            cell.layer, expected_layer,
                            cell.sublayer_index, expected_sublayer
                        )
                    )
                    cell.layer = expected_layer
                    cell.sublayer_index = expected_sublayer
                    fixes_made += 1

        if fixes_made > 0:
            logger.info("Fixed layer structure for {} cells".format(fixes_made))

            # Log the corrected structure
            layers = plan.get_cells_by_layer()
            parallel_layers = [l for l, cells in layers.items() if len(cells) > 1]
            if parallel_layers:
                logger.info("Corrected plan has {} layers with parallelization in: {}".format(
                    len(layers), parallel_layers
                ))
        else:
            logger.info("Layer structure was already correct, no fixes needed")

    def _validate_plan(self, plan: WorkflowPlan) -> None:
        """
        Validate that the plan is coherent and executable.

        Checks:
        - At least one cell exists
        - Final cell (highest layer) produces 'final_result'
        - Dependencies are satisfiable
        - Layer structure is valid

        Args:
            plan: The plan to validate

        Raises:
            Exception: If validation fails
        """
        if not plan.cells:
            raise Exception("Plan must have at least one cell")

        # Find the cell(s) in the highest layer - one of them should produce final_result
        max_layer = plan.get_max_layer()
        final_layer_cells = [c for c in plan.cells if c.layer == max_layer]

        # Check that at least one cell in the final layer produces final_result
        has_final_result = any(
            "final_result" in cell.outputs_produced
            for cell in final_layer_cells
        )

        if not has_final_result:
            # Add final_result to the last cell in the highest layer
            last_cell = final_layer_cells[-1] if final_layer_cells else plan.cells[-1]
            logger.warning(
                "No cell in final layer produces 'final_result', adding to '{}'".format(
                    last_cell.name
                )
            )
            last_cell.outputs_produced.append("final_result")

        # FIX SAME-LAYER DEPENDENCIES
        # Detect and repair cells that depend on outputs from other cells in the same layer.
        # These cells should be moved to a later layer since parallel cells can't depend on each other.
        max_iterations = 50  # Prevent infinite loops
        for iteration in range(max_iterations):
            layers = plan.get_cells_by_layer()
            made_changes = False

            for layer_num in sorted(layers.keys()):
                layer_cells = layers[layer_num]
                if len(layer_cells) <= 1:
                    continue

                # Build output map for this layer
                outputs_in_layer = {}  # output_name -> cell that produces it
                for cell in layer_cells:
                    for output in cell.outputs_produced:
                        outputs_in_layer[output] = cell

                # Check each cell for same-layer dependencies
                for cell in layer_cells:
                    for required_input in cell.inputs_required:
                        if required_input in outputs_in_layer:
                            producing_cell = outputs_in_layer[required_input]
                            if producing_cell != cell:
                                # This cell depends on another cell in the same layer
                                # Move this cell to the next layer
                                new_layer = layer_num + 1
                                logger.info(
                                    "Fixing same-layer dependency: Moving '{}' from layer {} to {} "
                                    "(needs '{}' from '{}')".format(
                                        cell.name, layer_num, new_layer,
                                        required_input, producing_cell.name
                                    )
                                )
                                cell.layer = new_layer
                                # Shift all subsequent layers
                                for other_cell in plan.cells:
                                    if other_cell.layer >= new_layer and other_cell != cell:
                                        other_cell.layer += 1
                                made_changes = True
                                break
                    if made_changes:
                        break
                if made_changes:
                    break

            if not made_changes:
                break  # No more fixes needed

            # Renumber sublayer indices after moving cells
            layers = plan.get_cells_by_layer()
            for layer_num in sorted(layers.keys()):
                layer_cells = layers[layer_num]
                for idx, cell in enumerate(sorted(layer_cells, key=lambda c: c.sublayer_index), 1):
                    cell.sublayer_index = idx

        if iteration == max_iterations - 1:
            logger.warning("Hit max iterations while fixing same-layer dependencies")

        # Validate layer structure
        layers = plan.get_cells_by_layer()
        for layer_num in sorted(layers.keys()):
            layer_cells = layers[layer_num]

            # Check sublayer indices are sequential
            sublayer_indices = [c.sublayer_index for c in layer_cells]
            expected = list(range(1, len(layer_cells) + 1))
            if sorted(sublayer_indices) != expected:
                logger.warning(
                    "Layer {} has non-sequential sublayer indices: {}".format(
                        layer_num, sublayer_indices
                    )
                )
                # Fix the indices
                for idx, cell in enumerate(layer_cells, 1):
                    cell.sublayer_index = idx

        # Check dependency chain (layer-aware)
        # Variables available after each layer completes
        available_vars = {"user_input", "attached_file_ids"}

        for layer_num in sorted(layers.keys()):
            layer_cells = layers[layer_num]

            # All cells in this layer can access variables from previous layers
            for cell in layer_cells:
                missing = set(cell.inputs_required) - available_vars
                if missing:
                    logger.warning(
                        "Cell '{}' (layer {}) requires unavailable inputs: {}".format(
                            cell.name, layer_num, missing
                        )
                    )

            # After this layer completes, all outputs become available
            for cell in layer_cells:
                available_vars.update(cell.outputs_produced)

        # Log parallelization info
        if plan.is_parallel_workflow():
            parallel_layers = [
                layer_num for layer_num, cells in layers.items()
                if len(cells) > 1
            ]
            logger.info(
                "Plan has {} layers with parallelization in layers: {}".format(
                    len(layers), parallel_layers
                )
            )
        else:
            logger.info("Plan has {} sequential layers".format(len(layers)))

        logger.info("Plan validation passed")


# Global planner instance
workflow_planner = WorkflowPlanner()
