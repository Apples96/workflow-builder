"""Assertion engine for evaluating workflow execution results.

Each assertion type checks a specific aspect of workflow output.
Assertions are designed to handle stochastic LLM output — they check
structure and presence, not exact values.
"""

import json
import os
import re
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class AssertionResult:
    """Result of running a single assertion."""

    def __init__(self, passed: bool, assertion_type: str, detail: str = ""):
        self.passed = passed
        self.assertion_type = assertion_type
        self.detail = detail

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.assertion_type,
            "passed": self.passed,
            "detail": self.detail
        }


def _find_cell_by_name(cells: List[Dict], name_contains: str) -> Optional[Dict]:
    """Find a cell whose name contains the given substring (case-insensitive)."""
    name_lower = name_contains.lower()
    for cell in cells:
        if name_lower in cell.get("name", "").lower():
            return cell
    return None


def _get_cell_output_variable(cell: Dict, variable_name: str) -> Any:
    """Get an output variable from a cell's output_variables dict."""
    variables = cell.get("output_variables") or {}
    return variables.get(variable_name)


def assert_all_cells_completed(plan: Dict, assertion: Dict) -> AssertionResult:
    """Check that all cells have status 'completed'."""
    cells = plan.get("cells", [])
    failed_cells = [c for c in cells if c.get("status") != "completed"]
    if failed_cells:
        names = [c.get("name", "?") for c in failed_cells]
        statuses = [c.get("status", "?") for c in failed_cells]
        detail = "Failed cells: {}".format(
            ", ".join("{} ({})".format(n, s) for n, s in zip(names, statuses)))
        return AssertionResult(False, "all_cells_completed", detail)
    return AssertionResult(True, "all_cells_completed",
                           "{} cells all completed".format(len(cells)))


def assert_no_cell_failed(plan: Dict, assertion: Dict) -> AssertionResult:
    """Check that no cell has status 'failed'."""
    cells = plan.get("cells", [])
    failed_cells = [c for c in cells if c.get("status") == "failed"]
    if failed_cells:
        names = [c.get("name", "?") for c in failed_cells]
        errors = [c.get("error", "?") for c in failed_cells]
        detail = "Failed: {}".format(
            ", ".join("{} ({})".format(n, e[:100]) for n, e in zip(names, errors)))
        return AssertionResult(False, "no_cell_failed", detail)
    return AssertionResult(True, "no_cell_failed", "No cells failed")


def assert_cell_has_output(plan: Dict, assertion: Dict) -> AssertionResult:
    """Check that a specific cell has a specific output variable."""
    cell_name_contains = assertion.get("cell_name_contains", "")
    output_variable = assertion.get("output_variable", "")
    check = assertion.get("check", "not_empty")

    cells = plan.get("cells", [])

    # When no cell name filter is given, search ALL cells for the output variable
    if not cell_name_contains:
        for candidate in cells:
            value = _get_cell_output_variable(candidate, output_variable)
            if value is not None:
                cell = candidate
                break
        else:
            return AssertionResult(False, "cell_has_output",
                                   "Variable '{}' not found in any cell".format(output_variable))
    else:
        cell = _find_cell_by_name(cells, cell_name_contains)
        if not cell:
            return AssertionResult(False, "cell_has_output",
                                   "No cell found matching '{}'".format(cell_name_contains))

    value = _get_cell_output_variable(cell, output_variable)
    if value is None:
        return AssertionResult(False, "cell_has_output",
                               "Variable '{}' not found in cell '{}'".format(
                                   output_variable, cell.get("name", "?")))

    if check == "not_empty":
        if not value or (isinstance(value, str) and not value.strip()):
            return AssertionResult(False, "cell_has_output",
                                   "Variable '{}' is empty".format(output_variable))
    elif check == "exists":
        pass  # Already checked above (not None)

    return AssertionResult(True, "cell_has_output",
                           "{} = '{}'".format(output_variable,
                                              str(value)[:200] if value else ""))


def assert_output_matches_pattern(plan: Dict, assertion: Dict) -> AssertionResult:
    """Check that an output variable matches a regex pattern."""
    cell_name_contains = assertion.get("cell_name_contains", "")
    output_variable = assertion.get("output_variable", "")
    pattern = assertion.get("pattern", "")

    cells = plan.get("cells", [])

    # When no cell name filter is given, search ALL cells for the output variable
    if not cell_name_contains:
        cell = None
        for candidate in cells:
            if _get_cell_output_variable(candidate, output_variable) is not None:
                cell = candidate
                break
        if not cell:
            return AssertionResult(False, "output_matches_pattern",
                                   "Variable '{}' not found in any cell".format(output_variable))
    else:
        cell = _find_cell_by_name(cells, cell_name_contains)
        if not cell:
            return AssertionResult(False, "output_matches_pattern",
                                   "No cell found matching '{}'".format(cell_name_contains))

    value = _get_cell_output_variable(cell, output_variable)
    if value is None:
        return AssertionResult(False, "output_matches_pattern",
                               "Variable '{}' not found".format(output_variable))

    value_str = str(value)
    if re.search(pattern, value_str):
        return AssertionResult(True, "output_matches_pattern",
                               "'{}' matches pattern '{}'".format(value_str[:100], pattern))
    return AssertionResult(False, "output_matches_pattern",
                           "'{}' does not match pattern '{}'".format(value_str[:100], pattern))


def assert_has_parallel_layer(plan: Dict, assertion: Dict) -> AssertionResult:
    """Check that at least one layer has more than one cell."""
    cells = plan.get("cells", [])
    layers = {}
    for cell in cells:
        layer = cell.get("layer", 1)
        layers.setdefault(layer, []).append(cell)

    parallel_layers = {k: len(v) for k, v in layers.items() if len(v) > 1}
    if parallel_layers:
        detail = "Parallel layers: {}".format(
            ", ".join("layer {} ({} cells)".format(k, v) for k, v in parallel_layers.items()))
        return AssertionResult(True, "has_parallel_layer", detail)
    return AssertionResult(False, "has_parallel_layer",
                           "No parallel layers found (all layers have 1 cell)")


def assert_cell_count_gte(plan: Dict, assertion: Dict) -> AssertionResult:
    """Check that the workflow has at least min_cells cells."""
    min_cells = assertion.get("min_cells", 1)
    actual = len(plan.get("cells", []))
    passed = actual >= min_cells
    return AssertionResult(passed, "cell_count_gte",
                           "{} cells (min: {})".format(actual, min_cells))


def assert_cell_count_lte(plan: Dict, assertion: Dict) -> AssertionResult:
    """Check that the workflow has at most max_cells cells."""
    max_cells = assertion.get("max_cells", 100)
    actual = len(plan.get("cells", []))
    passed = actual <= max_cells
    return AssertionResult(passed, "cell_count_lte",
                           "{} cells (max: {})".format(actual, max_cells))


def assert_total_time_under(plan: Dict, assertion: Dict, total_time: float = 0) -> AssertionResult:
    """Check that total execution time is under the threshold."""
    max_seconds = assertion.get("max_seconds", 600)
    passed = total_time <= max_seconds
    return AssertionResult(passed, "total_time_under",
                           "{:.0f}s (max: {}s)".format(total_time, max_seconds))


def assert_cell_uses_tool(plan: Dict, assertion: Dict) -> AssertionResult:
    """Check that a specific cell uses a specific Paradigm tool."""
    cell_name_contains = assertion.get("cell_name_contains", "")
    tool = assertion.get("tool", "")

    cells = plan.get("cells", [])
    cell = _find_cell_by_name(cells, cell_name_contains)
    if not cell:
        return AssertionResult(False, "cell_uses_tool",
                               "No cell found matching '{}'".format(cell_name_contains))

    tools_used = cell.get("paradigm_tools_used", [])
    if tool in tools_used:
        return AssertionResult(True, "cell_uses_tool",
                               "Cell '{}' uses tool '{}'".format(cell.get("name"), tool))
    return AssertionResult(False, "cell_uses_tool",
                           "Cell '{}' does not use '{}' (uses: {})".format(
                               cell.get("name"), tool, tools_used))


def assert_llm_judge(plan: Dict, assertion: Dict) -> AssertionResult:
    """Use an LLM to judge output quality. Requires ANTHROPIC_API_KEY env var.

    Assertion config:
        cell_name_contains: str — which cell to evaluate
        prompt: str — evaluation prompt describing what to check
        pass_threshold: float — score (0-1) required to pass (default 0.7)
    """
    cell_name_contains = assertion.get("cell_name_contains", "")
    prompt = assertion.get("prompt", "")
    pass_threshold = assertion.get("pass_threshold", 0.7)

    if not prompt:
        return AssertionResult(False, "llm_judge", "No prompt provided")

    cells = plan.get("cells", [])
    cell = _find_cell_by_name(cells, cell_name_contains) if cell_name_contains else None

    # Build context for the judge
    if cell:
        output_vars = cell.get("output_variables") or {}
        cell_output = cell.get("output", "")
        context = "Cell: {}\nOutput: {}\nVariables: {}".format(
            cell.get("name", "?"), cell_output[:2000] if cell_output else "",
            json.dumps(output_vars, default=str)[:3000])
    else:
        # Judge the whole workflow
        all_outputs = []
        for c in cells:
            vars_str = json.dumps(c.get("output_variables") or {}, default=str)[:500]
            all_outputs.append("{}: {}".format(c.get("name", "?"), vars_str))
        context = "All cell outputs:\n{}".format("\n".join(all_outputs))

    try:
        import anthropic
    except ImportError:
        return AssertionResult(False, "llm_judge", "anthropic package not installed")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return AssertionResult(False, "llm_judge", "ANTHROPIC_API_KEY not set")

    try:
        client = anthropic.Anthropic(api_key=api_key)

        # Use tool_use for structured response
        judge_tool = {
            "name": "submit_judgment",
            "description": "Submit your judgment of the output quality.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "score": {
                        "type": "number",
                        "description": "Quality score from 0.0 (terrible) to 1.0 (perfect)."
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Brief explanation of the score."
                    }
                },
                "required": ["score", "reasoning"]
            }
        }

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            system="You are an eval judge. Evaluate the output quality based on the criteria given. Use the submit_judgment tool.",
            messages=[{
                "role": "user",
                "content": "CRITERIA:\n{}\n\nOUTPUT TO EVALUATE:\n{}".format(prompt, context)
            }],
            tools=[judge_tool],
            tool_choice={"type": "tool", "name": "submit_judgment"},
            timeout=30.0
        )

        # Extract tool result
        for block in response.content:
            if block.type == "tool_use" and block.name == "submit_judgment":
                score = float(block.input.get("score", 0))
                reasoning = block.input.get("reasoning", "")
                passed = score >= pass_threshold
                return AssertionResult(
                    passed, "llm_judge",
                    "score={:.2f} (threshold={}) — {}".format(score, pass_threshold, reasoning[:200]))

        return AssertionResult(False, "llm_judge", "No tool_use response from judge")

    except Exception as e:
        return AssertionResult(False, "llm_judge", "LLM judge error: {}".format(str(e)))


# Registry mapping assertion type names to their handler functions
ASSERTION_REGISTRY = {
    "all_cells_completed": assert_all_cells_completed,
    "no_cell_failed": assert_no_cell_failed,
    "cell_has_output": assert_cell_has_output,
    "output_matches_pattern": assert_output_matches_pattern,
    "has_parallel_layer": assert_has_parallel_layer,
    "cell_count_gte": assert_cell_count_gte,
    "cell_count_lte": assert_cell_count_lte,
    "total_time_under": assert_total_time_under,
    "cell_uses_tool": assert_cell_uses_tool,
    "llm_judge": assert_llm_judge,
}


def run_assertions(
    plan: Dict,
    assertions: List[Dict],
    total_time: float = 0
) -> List[AssertionResult]:
    """Run all assertions against a workflow plan and return results."""
    results = []
    for assertion in assertions:
        assertion_type = assertion.get("type", "")
        handler = ASSERTION_REGISTRY.get(assertion_type)
        if not handler:
            results.append(AssertionResult(False, assertion_type,
                                           "Unknown assertion type: {}".format(assertion_type)))
            continue

        try:
            if assertion_type == "total_time_under":
                result = handler(plan, assertion, total_time=total_time)
            else:
                result = handler(plan, assertion)
            results.append(result)
        except Exception as e:
            logger.error("Assertion '{}' raised exception: {}".format(assertion_type, e))
            results.append(AssertionResult(False, assertion_type,
                                           "Error: {}".format(str(e))))
    return results
