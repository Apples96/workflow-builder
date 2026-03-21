"""Cell-based workflow planner: breaks user descriptions into executable cell plans."""

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
    """Extract STEP X.Y patterns from description into (layer, sublayer_index) tuples."""
    layer_structure = {}

    # Matches "STEP X.Y:" / "STEP X.Y -" variants
    step_pattern = re.compile(r'STEP\s+(\d+)\.(\d+)\s*[:\-]', re.IGNORECASE)

    for match in step_pattern.finditer(description):
        layer = int(match.group(1))
        sublayer = int(match.group(2))
        step_id = "{}.{}".format(layer, sublayer)
        layer_structure[step_id] = (layer, sublayer)
        logger.debug("Parsed step {} -> layer={}, sublayer={}".format(step_id, layer, sublayer))

    if layer_structure:
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
    """Load the workflow planner system prompt from markdown file."""
    return PromptLoader.load("planner")


class WorkflowPlanner:
    """Creates workflow plans from natural language descriptions using Claude."""

    def __init__(self, anthropic_client=None):
        self.anthropic_client = anthropic_client or create_anthropic_client()

    async def create_plan(
        self,
        description: str,
        context: Optional[Dict[str, Any]] = None,
        output_example: Optional[str] = None
    ) -> WorkflowPlan:
        """Create a workflow plan from a natural language description."""
        logger.info("Creating workflow plan for: {}...".format(description[:100]))

        system_prompt = load_planner_prompt()
        if not system_prompt:
            raise Exception("Could not load planner system prompt")

        user_message = self._build_user_message(description, context, output_example)

        try:
            # Parse expected layer structure before calling Claude so we can fix mismatches
            expected_layer_structure = parse_layer_structure_from_description(description)

            if expected_layer_structure:
                logger.info("Parsed expected layer structure with {} steps from description".format(
                    len(expected_layer_structure)
                ))
            else:
                logger.info("No STEP X.Y pattern found in description, using Claude's layer assignments")

            response = self.anthropic_client.messages.create(
                model=settings.anthropic_model,
                max_tokens=settings.anthropic_max_tokens_plan,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
                timeout=max(settings.anthropic_timeout, 300)
            )

            raw_output = response.content[0].text
            stop_reason = response.stop_reason
            logger.info("Raw planner output: {}".format(raw_output[:500]))

            if stop_reason == "max_tokens":
                logger.warning(
                    "Planner response was TRUNCATED (hit max_tokens={}). "
                    "Output length: {} chars. Will attempt JSON repair.".format(
                        settings.anthropic_max_tokens_plan, len(raw_output)
                    )
                )

            plan_data = self._parse_plan_output(raw_output)

            plan = self._create_plan_from_data(
                plan_data, description, expected_layer_structure, output_example
            )

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
        context: Optional[Dict[str, Any]] = None,
        output_example: Optional[str] = None
    ) -> str:
        """Build the user message for the planning request."""
        message_parts = [
            "Create a workflow plan for the following description:",
            "",
            "WORKFLOW DESCRIPTION:",
            description,
            ""
        ]

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

        if output_example:
            message_parts.append("OUTPUT EXAMPLE (for deriving final cell success criteria):")
            message_parts.append("")
            message_parts.append("The user has provided this example of their desired output format:")
            message_parts.append("```")
            message_parts.append(output_example)
            message_parts.append("```")
            message_parts.append("")
            message_parts.append("IMPORTANT: Use this example to derive success_criteria for the FINAL CELL ONLY.")
            message_parts.append("- Identify the format type (table, list, JSON, prose, etc.)")
            message_parts.append("- Identify structural elements (columns, sections, required fields)")
            message_parts.append("- Create verifiable criteria based on structure, NOT content")
            message_parts.append("- Intermediate cells should use standard criteria based on their descriptions")
            message_parts.append("")

        message_parts.append(
            "Generate a JSON plan with discrete cells for this workflow."
        )

        return "\n".join(message_parts)

    def _parse_plan_output(self, raw_output: str) -> Dict[str, Any]:
        """Parse the JSON plan from Claude's raw output, handling markdown and truncation."""
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

            if error_pos:
                start = max(0, error_pos - 200)
                end = min(len(cleaned), error_pos + 200)
                context = cleaned[start:end]
                logger.error("Context around error: ...{}...".format(context))

            try:
                import tempfile
                with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                    f.write(raw_output)
                    logger.error("Full output saved to: {}".format(f.name))
            except:
                logger.error("Full raw output (first 2000 chars): {}".format(raw_output[:2000]))

            fixed_json = self._try_fix_json(cleaned)
            if fixed_json:
                try:
                    result = json.loads(fixed_json)
                    logger.info("Successfully parsed JSON after auto-fix")
                    return result
                except json.JSONDecodeError:
                    logger.error("Auto-fix failed")

            # Fallback: extract outermost JSON object with regex
            json_match = re.search(r'\{[\s\S]*\}', raw_output)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass

            raise Exception("Failed to parse workflow plan: {}".format(str(e)))

    def _try_fix_json(self, json_str: str) -> Optional[str]:
        """Attempt to fix trailing commas and truncated structures in malformed JSON."""
        try:
            fixed = re.sub(r',(\s*[}\]])', r'\1', json_str)
            fixed = self._close_truncated_json(fixed)

            return fixed
        except Exception as e:
            logger.error("JSON auto-fix error: {}".format(e))
            return None

    def _close_truncated_json(self, json_str: str) -> str:
        """Close truncated JSON by tracking open structures and appending missing closers."""
        stack = []
        in_string = False
        escape_next = False
        i = 0

        while i < len(json_str):
            char = json_str[i]

            if escape_next:
                escape_next = False
                i += 1
                continue

            if char == '\\' and in_string:
                escape_next = True
                i += 1
                continue

            if char == '"':
                in_string = not in_string
                i += 1
                continue

            if not in_string:
                if char == '{':
                    stack.append('}')
                elif char == '[':
                    stack.append(']')
                elif char in ('}', ']'):
                    if stack and stack[-1] == char:
                        stack.pop()

            i += 1

        if in_string:
            last_quote = json_str.rfind('"')
            if last_quote > 0:
                before_quote = json_str[:last_quote].rstrip()
                if before_quote.endswith(':'):
                    json_str = json_str[:last_quote] + '""'
                else:
                    json_str = json_str + '"'

        json_str = json_str.rstrip()
        if json_str.endswith(','):
            json_str = json_str[:-1]

        if stack:
            logger.info("Closing {} unclosed JSON structures".format(len(stack)))
            json_str = json_str.rstrip().rstrip(',')
            json_str += ''.join(reversed(stack))

        return json_str

    def _create_plan_from_data(
        self,
        plan_data: Dict[str, Any],
        description: str,
        expected_layer_structure: Optional[Dict[str, Tuple[int, int]]] = None,
        output_example: Optional[str] = None
    ) -> WorkflowPlan:
        """Create a WorkflowPlan from parsed JSON data and apply layer structure fixes."""
        plan = WorkflowPlan(
            description=description,
            shared_context_schema=plan_data.get("shared_context_schema", {}),
            output_example=output_example,
            status="ready"
        )

        cells_data = plan_data.get("cells", [])
        for cell_data in cells_data:
            cell = WorkflowCell(
                workflow_id=plan.workflow_id,
                step_number=cell_data.get("step_number", 0),
                name=cell_data.get("name", "Unnamed Step"),
                description=cell_data.get("description", ""),
                layer=cell_data.get("layer", 1),
                sublayer_index=cell_data.get("sublayer_index", 1),
                depends_on=cell_data.get("depends_on", []),
                inputs_required=cell_data.get("inputs_required", []),
                outputs_produced=cell_data.get("outputs_produced", []),
                paradigm_tools_used=cell_data.get("paradigm_tools_used", []),
                success_criteria=cell_data.get("success_criteria"),
                status=CellStatus.PENDING
            )
            plan.cells.append(cell)

        if expected_layer_structure:
            self._fix_layer_structure(plan, expected_layer_structure)

        self._validate_plan(plan)

        return plan

    def _fix_layer_structure(
        self,
        plan: WorkflowPlan,
        expected_structure: Dict[str, Tuple[int, int]]
    ) -> None:
        """Fix cell layer assignments to match the STEP X.Y structure from the description."""
        if not expected_structure:
            logger.info("No expected structure provided, skipping layer fix")
            return

        # Cells are assumed to be in the same order as they appear in the description
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

        fixes_made = 0

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

            layers = plan.get_cells_by_layer()
            parallel_layers = [l for l, cells in layers.items() if len(cells) > 1]
            if parallel_layers:
                logger.info("Corrected plan has {} layers with parallelization in: {}".format(
                    len(layers), parallel_layers
                ))
        else:
            logger.info("Layer structure was already correct, no fixes needed")

    def _validate_plan(self, plan: WorkflowPlan) -> None:
        """Validate plan coherence: cell existence, final_result output, dependencies, and layer structure."""
        if not plan.cells:
            raise Exception("Plan must have at least one cell")

        max_layer = plan.get_max_layer()
        final_layer_cells = [c for c in plan.cells if c.layer == max_layer]

        has_final_result = any(
            "final_result" in cell.outputs_produced
            for cell in final_layer_cells
        )

        if not has_final_result:
            last_cell = final_layer_cells[-1] if final_layer_cells else plan.cells[-1]
            logger.warning(
                "No cell in final layer produces 'final_result', adding to '{}'".format(
                    last_cell.name
                )
            )
            last_cell.outputs_produced.append("final_result")

        # Parallel cells can't depend on each other; move violators to later layers
        max_iterations = 50
        for iteration in range(max_iterations):
            layers = plan.get_cells_by_layer()
            made_changes = False

            for layer_num in sorted(layers.keys()):
                layer_cells = layers[layer_num]
                if len(layer_cells) <= 1:
                    continue

                outputs_in_layer = {}
                for cell in layer_cells:
                    for output in cell.outputs_produced:
                        outputs_in_layer[output] = cell

                for cell in layer_cells:
                    for required_input in cell.inputs_required:
                        if required_input in outputs_in_layer:
                            producing_cell = outputs_in_layer[required_input]
                            if producing_cell != cell:
                                new_layer = layer_num + 1
                                logger.info(
                                    "Fixing same-layer dependency: Moving '{}' from layer {} to {} "
                                    "(needs '{}' from '{}')".format(
                                        cell.name, layer_num, new_layer,
                                        required_input, producing_cell.name
                                    )
                                )
                                cell.layer = new_layer
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
                break

            layers = plan.get_cells_by_layer()
            for layer_num in sorted(layers.keys()):
                layer_cells = layers[layer_num]
                for idx, cell in enumerate(sorted(layer_cells, key=lambda c: c.sublayer_index), 1):
                    cell.sublayer_index = idx

        if iteration == max_iterations - 1:
            logger.warning("Hit max iterations while fixing same-layer dependencies")

        layers = plan.get_cells_by_layer()
        for layer_num in sorted(layers.keys()):
            layer_cells = layers[layer_num]

            sublayer_indices = [c.sublayer_index for c in layer_cells]
            expected = list(range(1, len(layer_cells) + 1))
            if sorted(sublayer_indices) != expected:
                logger.warning(
                    "Layer {} has non-sequential sublayer indices: {}".format(
                        layer_num, sublayer_indices
                    )
                )
                for idx, cell in enumerate(layer_cells, 1):
                    cell.sublayer_index = idx

        # Check dependency chain: track variables available after each layer completes
        available_vars = {"user_input", "attached_file_ids"}

        for layer_num in sorted(layers.keys()):
            layer_cells = layers[layer_num]

            for cell in layer_cells:
                missing = set(cell.inputs_required) - available_vars
                if missing:
                    logger.warning(
                        "Cell '{}' (layer {}) requires unavailable inputs: {}".format(
                            cell.name, layer_num, missing
                        )
                    )

            for cell in layer_cells:
                available_vars.update(cell.outputs_produced)

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
