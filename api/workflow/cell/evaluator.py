"""Cell output evaluation using Claude as a judge (LLM-as-a-Judge pattern)."""

import logging
from dataclasses import dataclass
from typing import Dict, Any, List, Optional

from ..models import WorkflowCell
from ...clients import create_anthropic_client
from ...config import settings
from ..prompts.loader import PromptLoader

def _get_eval_output_max_chars() -> int:
    """Get the configurable output truncation limit (read at call time, not import time).

    Controlled via EVAL_OUTPUT_MAX_CHARS env var, default 4000.
    """
    return settings.eval_output_max_chars

logger = logging.getLogger(__name__)

# Tool schema for structured evaluation output via Anthropic tool_use
EVALUATION_TOOL = {
    "name": "submit_evaluation",
    "description": "Submit a structured evaluation of the cell output.",
    "input_schema": {
        "type": "object",
        "properties": {
            "is_valid": {
                "type": "boolean",
                "description": "Whether the cell output passes evaluation (true) or fails (false)."
            },
            "confidence": {
                "type": "number",
                "description": "Confidence in this evaluation judgment, from 0.0 (very uncertain) to 1.0 (completely certain)."
            },
            "score": {
                "type": "number",
                "description": "Overall quality score of the cell output, from 0.0 (completely wrong) to 1.0 (perfect). A cell can be valid (is_valid=true) but still have a mediocre score (e.g. 0.7)."
            },
            "feedback": {
                "type": "string",
                "description": "Detailed feedback explaining the evaluation. Be specific about what was checked and why."
            },
            "issues": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of specific issues found. Empty array if no issues."
            },
            "output_analysis": {
                "type": "string",
                "description": "If is_valid is false, detailed analysis of what is wrong with the output. 'None' if no issues."
            },
            "field_scores": {
                "type": "object",
                "additionalProperties": {"type": "number"},
                "description": "Per-output-variable quality scores (0.0-1.0). Include a score for each output variable that was evaluated."
            }
        },
        "required": ["is_valid", "confidence", "score", "feedback", "issues"]
    }
}


@dataclass
class ExampleOutput:
    """Output data for a single example execution."""
    example_id: str
    user_input: str
    output_text: str
    output_variables: Dict[str, Any]
    formatted_variables: Dict[str, str]


@dataclass
class EvaluationResult:
    """Result of evaluating cell outputs."""
    is_valid: bool
    feedback: str
    issues: List[str]
    output_analysis: Optional[str] = None
    confidence: float = 1.0  # 0.0-1.0 — evaluator's confidence in its judgment
    score: float = 1.0  # 0.0-1.0 — overall quality score of the cell output
    field_scores: Optional[Dict[str, float]] = None  # per-output-variable scores


def load_evaluator_prompt() -> str:
    """Load the evaluation system prompt from markdown file."""
    return PromptLoader.load_optional("evaluator")


class CellOutputEvaluator:
    """Evaluates cell outputs using Claude as a judge."""

    def __init__(
        self,
        anthropic_client=None,
        max_evaluation_retries: int = 5
    ):
        self.anthropic_client = anthropic_client or create_anthropic_client()
        self.max_evaluation_retries = max_evaluation_retries

    async def evaluate_smoke_test_output(
        self,
        cell: WorkflowCell,
        smoke_test_output: ExampleOutput,
        workflow_description: str,
        cell_code: str,
        output_example: Optional[str] = None
    ) -> EvaluationResult:
        """Evaluate the output from a smoke test (first example) execution."""
        logger.info("Evaluating smoke test output for cell '{}'".format(cell.name))

        system_prompt = load_evaluator_prompt()
        if not system_prompt:
            system_prompt = self._get_default_system_prompt()

        user_message = self._build_smoke_test_message(
            cell=cell,
            smoke_test_output=smoke_test_output,
            workflow_description=workflow_description,
            cell_code=cell_code,
            output_example=output_example
        )

        try:
            response = self.anthropic_client.messages.create(
                model=settings.anthropic_model,
                max_tokens=4000,
                system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user_message}],
                tools=[EVALUATION_TOOL],
                tool_choice={"type": "tool", "name": "submit_evaluation"},
                timeout=settings.anthropic_timeout
            )

            return self._parse_tool_use_response(response)

        except Exception as e:
            logger.error("Evaluation failed: {}".format(str(e)))
            return EvaluationResult(
                is_valid=True,
                feedback="Evaluation skipped due to error: {}".format(str(e)),
                issues=[]
            )

    async def evaluate_all_examples_output(
        self,
        cell: WorkflowCell,
        example_outputs: List[ExampleOutput],
        workflow_description: str,
        cell_code: str,
        output_example: Optional[str] = None
    ) -> EvaluationResult:
        """Evaluate outputs from ALL examples together for pattern-based evaluation."""
        logger.info("Evaluating {} examples output for cell '{}'".format(
            len(example_outputs), cell.name
        ))

        system_prompt = load_evaluator_prompt()
        if not system_prompt:
            system_prompt = self._get_default_system_prompt()

        user_message = self._build_all_examples_message(
            cell=cell,
            example_outputs=example_outputs,
            workflow_description=workflow_description,
            cell_code=cell_code,
            output_example=output_example
        )

        try:
            response = self.anthropic_client.messages.create(
                model=settings.anthropic_model,
                max_tokens=4000,
                system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user_message}],
                tools=[EVALUATION_TOOL],
                tool_choice={"type": "tool", "name": "submit_evaluation"},
                timeout=settings.anthropic_timeout
            )

            return self._parse_tool_use_response(response)

        except Exception as e:
            logger.error("All-examples evaluation failed: {}".format(str(e)))
            return EvaluationResult(
                is_valid=True,
                feedback="Evaluation skipped due to error: {}".format(str(e)),
                issues=[]
            )

    def _get_default_system_prompt(self) -> str:
        """Get default system prompt for evaluation if prompt file not found."""
        return """You are an expert code output evaluator for workflow automation systems.
Your job is to evaluate whether the output from a workflow cell is correct and sensible.

You will receive:
1. The cell's purpose and expected behavior
2. The output from a test example (smoke test)
3. The generated cell code
4. The workflow context

Your task is to determine if the output is:
- Well-formed (correct data types, not unexpectedly empty when data was expected)
- Consistent with the cell's stated purpose
- Sensible given the input
- Free from obvious errors or anomalies

IMPORTANT GUIDELINES:
- Be practical and reasonable in your evaluation
- Empty results are OK if the query/input legitimately returns no matches
- Focus on structural/functional issues, not subjective quality
- Don't fail outputs just because they could be "better"
- Fail only when there are clear problems:
  - Wrong data type returned
  - Missing required fields
  - Obvious runtime errors in the output
  - Output contradicts the cell's purpose
  - Data that is clearly corrupted or malformed

TRUNCATED OUTPUTS: If you see a [TRUNCATED: showing X of Y total characters...] notice,
evaluate only the visible portion. Do NOT fail because later sections appear missing —
they likely exist beyond the truncation boundary. Only fail for problems in the visible content.

Use the submit_evaluation tool to submit your structured evaluation. Provide:
- is_valid: true/false
- confidence: 0.0-1.0 (how confident you are in your judgment)
- score: 0.0-1.0 (overall quality of the output — 1.0 is perfect, 0.0 is completely wrong)
- feedback: detailed explanation of your evaluation
- issues: list of specific problems found (empty list if none)
- output_analysis: if invalid, what is wrong with the output
- field_scores: per-output-variable scores (0.0-1.0)"""

    def _truncate_with_notice(self, text: str, max_chars: int, label: str = "output") -> str:
        """Truncate text and append a notice for the evaluator if truncation occurred.

        The notice tells the LLM judge the full length so it can evaluate
        fairly based on what is visible, without penalizing for 'missing' content.
        """
        if len(text) <= max_chars:
            return text
        return (
            text[:max_chars]
            + "\n\n[TRUNCATED: showing {shown} of {total} total characters for {label}. "
            "The full output is longer than what is shown here. Evaluate based on the visible "
            "portion only — do NOT fail because later sections are not visible.]"
        ).format(shown=max_chars, total=len(text), label=label)

    def _build_smoke_test_message(
        self,
        cell: WorkflowCell,
        smoke_test_output: ExampleOutput,
        workflow_description: str,
        cell_code: str,
        output_example: Optional[str] = None
    ) -> str:
        """Build the user message for smoke test evaluation."""
        variables_display = self._format_variables_for_display(
            smoke_test_output.formatted_variables
        )
        # Apply configurable truncation with evaluator-awareness
        output_text = smoke_test_output.output_text or "(no printed output)"
        output_text = self._truncate_with_notice(output_text, _get_eval_output_max_chars(), "printed output")
        variables_display = self._truncate_with_notice(variables_display, _get_eval_output_max_chars(), "output variables")

        message = """Please evaluate the following cell output from a smoke test execution:

WORKFLOW CONTEXT:
{workflow_description}

CELL INFORMATION:
- Name: {cell_name}
- Description: {cell_description}
- Expected Inputs: {inputs}
- Expected Outputs: {outputs}
- Paradigm Tools Used: {tools}

GENERATED CELL CODE:
```python
{cell_code}
```

SMOKE TEST EXECUTION:
- User Input: {user_input}

Printed Output (CELL_OUTPUT messages):
{output_text}

Output Variables:
{variables}

Please evaluate whether this output is correct and sensible. Consider:
1. Is the output well-formed (correct types, properly structured)?
2. Does the output match what the cell is supposed to produce?
3. Are there any obvious errors or anomalies?
4. If there are empty results, is that reasonable given the input?

Provide your evaluation using the submit_evaluation tool.""".format(
            workflow_description=workflow_description,
            cell_name=cell.name,
            cell_description=cell.description,
            inputs=", ".join(cell.inputs_required) if cell.inputs_required else "none",
            outputs=", ".join(cell.outputs_produced) if cell.outputs_produced else "none",
            tools=", ".join(cell.paradigm_tools_used) if cell.paradigm_tools_used else "none",
            cell_code=cell_code[:3000] if len(cell_code) > 3000 else cell_code,
            user_input=smoke_test_output.user_input[:500] if smoke_test_output.user_input else "(empty)",
            output_text=output_text,
            variables=variables_display
        )

        if cell.success_criteria:
            message += """

CELL-SPECIFIC SUCCESS CRITERIA:
{criteria}

Use these criteria IN ADDITION to the general guidelines when evaluating. The output should meet these specific requirements.""".format(
                criteria=cell.success_criteria
            )

        if output_example:
            message += """

OUTPUT FORMAT EXAMPLE (FINAL CELL):
The user provided this example of their desired output FORMAT:
```
{example}
```

IMPORTANT: This is a FORMAT reference, not expected content.
- Evaluate if the output uses a SIMILAR FORMAT (table/list/JSON/etc.)
- Check for SIMILAR STRUCTURE (columns, sections, elements)
- Do NOT require exact content match
- PASS if format/structure resembles the example
- FAIL only if format is structurally incompatible (e.g., prose when table expected)""".format(
                example=output_example
            )

        return message

    def _build_all_examples_message(
        self,
        cell: WorkflowCell,
        example_outputs: List[ExampleOutput],
        workflow_description: str,
        cell_code: str,
        output_example: Optional[str] = None
    ) -> str:
        """Build the user message for evaluating ALL examples together."""
        examples_text = ""
        # Use configurable limit; total scales with number of examples
        max_output_length = _get_eval_output_max_chars()
        max_total_length = _get_eval_output_max_chars() * 3  # Room for multiple examples

        for idx, example in enumerate(example_outputs, 1):
            variables_display = self._format_variables_for_display(example.formatted_variables)

            output_text = example.output_text or "(no printed output)"
            output_text = self._truncate_with_notice(output_text, max_output_length, "printed output")
            variables_display = self._truncate_with_notice(variables_display, max_output_length, "output variables")

            example_section = """
EXAMPLE {idx}:
- User Input: {user_input}
- Printed Output (CELL_OUTPUT messages):
{output_text}
- Output Variables:
{variables}
""".format(
                idx=idx,
                user_input=example.user_input[:500] if example.user_input else "(empty)",
                output_text=output_text,
                variables=variables_display
            )

            if len(examples_text) + len(example_section) > max_total_length:
                examples_text += "\n... ({} more examples truncated due to length)\n".format(
                    len(example_outputs) - idx + 1
                )
                break

            examples_text += example_section

        message = """Please evaluate the outputs from ALL {num_examples} example executions of this cell:

WORKFLOW CONTEXT:
{workflow_description}

CELL INFORMATION:
- Name: {cell_name}
- Description: {cell_description}
- Expected Inputs: {inputs}
- Expected Outputs: {outputs}
- Paradigm Tools Used: {tools}

GENERATED CELL CODE:
```python
{cell_code}
```

=== ALL EXAMPLE OUTPUTS ({num_examples} examples) ===
{examples_text}
=== END OF EXAMPLES ===

EVALUATION INSTRUCTIONS:
Please evaluate ALL outputs together and look for PATTERNS across examples:
1. Are all outputs well-formed (correct types, properly structured)?
2. Do outputs match what the cell is supposed to produce?
3. Are there any consistent issues across multiple examples?
4. Are there edge cases that fail while others succeed?
5. If some outputs are empty, is that reasonable given those specific inputs?

IMPORTANT: Consider patterns across ALL examples - a single failing example among many successes
may indicate an edge case bug. Multiple failures with similar issues indicate a systematic problem.

Provide your evaluation using the submit_evaluation tool.
In your feedback, reference specific examples when noting issues (e.g., "Example 2 and 4 both show...").""".format(
            num_examples=len(example_outputs),
            workflow_description=workflow_description,
            cell_name=cell.name,
            cell_description=cell.description,
            inputs=", ".join(cell.inputs_required) if cell.inputs_required else "none",
            outputs=", ".join(cell.outputs_produced) if cell.outputs_produced else "none",
            tools=", ".join(cell.paradigm_tools_used) if cell.paradigm_tools_used else "none",
            cell_code=cell_code[:3000] if len(cell_code) > 3000 else cell_code,
            examples_text=examples_text
        )

        if cell.success_criteria:
            message += """

CELL-SPECIFIC SUCCESS CRITERIA:
{criteria}

Use these criteria IN ADDITION to the general guidelines when evaluating all examples.
The output from each example should meet these specific requirements.""".format(
                criteria=cell.success_criteria
            )

        if output_example:
            message += """

OUTPUT FORMAT EXAMPLE (FINAL CELL):
The user provided this example of their desired output FORMAT:
```
{example}
```

IMPORTANT: This is a FORMAT reference, not expected content.
- Evaluate if ALL outputs use a SIMILAR FORMAT (table/list/JSON/etc.)
- Check for SIMILAR STRUCTURE (columns, sections, elements)
- Do NOT require exact content match
- PASS if format/structure resembles the example across all examples
- FAIL only if format is structurally incompatible (e.g., prose when table expected)""".format(
                example=output_example
            )

        return message

    def _format_variables_for_display(self, variables: Dict[str, str]) -> str:
        """Format variables dictionary for display in prompt."""
        if not variables:
            return "(no variables returned)"

        lines = []
        for name, value in variables.items():
            lines.append("  {}: {}".format(name, value))

        return "\n".join(lines)

    def _parse_tool_use_response(self, response) -> EvaluationResult:
        """Parse a tool_use response from Claude into an EvaluationResult."""
        try:
            # Find the tool_use block in the response
            tool_input = None
            for block in response.content:
                if block.type == "tool_use" and block.name == "submit_evaluation":
                    tool_input = block.input
                    break

            if tool_input is None:
                # Fallback: try to parse as text response
                logger.warning("No tool_use block found in evaluation response, falling back to text parsing")
                text_content = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        text_content += block.text
                if text_content:
                    return self._parse_evaluation_response(text_content)
                return EvaluationResult(
                    is_valid=True,
                    feedback="Could not parse evaluation response (no tool_use block)",
                    issues=[]
                )

            is_valid = tool_input.get("is_valid", True)
            confidence = float(tool_input.get("confidence", 1.0))
            score = float(tool_input.get("score", 1.0 if is_valid else 0.0))
            feedback = tool_input.get("feedback", "")
            issues = tool_input.get("issues", [])
            output_analysis = tool_input.get("output_analysis")
            field_scores = tool_input.get("field_scores")

            # Clamp values to valid range
            confidence = max(0.0, min(1.0, confidence))
            score = max(0.0, min(1.0, score))
            if field_scores:
                field_scores = {k: max(0.0, min(1.0, float(v))) for k, v in field_scores.items()}

            # Normalize output_analysis
            if output_analysis and output_analysis.lower() in ("none", "null", "n/a"):
                output_analysis = None

            logger.info("Evaluation result: valid={}, score={:.2f}, confidence={:.2f}, issues={}".format(
                is_valid, score, confidence, len(issues)))

            return EvaluationResult(
                is_valid=is_valid,
                feedback=feedback,
                issues=issues,
                output_analysis=output_analysis,
                confidence=confidence,
                score=score,
                field_scores=field_scores
            )

        except Exception as e:
            logger.warning("Error parsing tool_use evaluation response: {}".format(e))
            return EvaluationResult(
                is_valid=True,
                feedback="Could not parse evaluation response: {}".format(str(e)),
                issues=[]
            )

    def _parse_evaluation_response(self, response: str) -> EvaluationResult:
        """Parse Claude's evaluation response into an EvaluationResult."""
        is_valid = True
        feedback = ""
        issues = []
        output_analysis = None

        try:
            if "VALID:" in response:
                valid_line = response.split("VALID:")[1].split("\n")[0].strip().lower()
                is_valid = valid_line in ["true", "yes", "1", "valid", "pass"]

            if "FEEDBACK:" in response:
                feedback_start = response.find("FEEDBACK:") + len("FEEDBACK:")
                feedback_end = response.find("ISSUES:")
                if feedback_end == -1:
                    feedback_end = response.find("OUTPUT_ANALYSIS:")
                if feedback_end == -1:
                    feedback_end = len(response)
                feedback = response[feedback_start:feedback_end].strip()

            if "ISSUES:" in response:
                issues_start = response.find("ISSUES:") + len("ISSUES:")
                issues_end = response.find("OUTPUT_ANALYSIS:")
                if issues_end == -1:
                    issues_end = len(response)
                issues_text = response[issues_start:issues_end].strip()

                if issues_text.lower() != "none":
                    # Parse bullet points
                    for line in issues_text.split("\n"):
                        line = line.strip()
                        if line.startswith("-") or line.startswith("*"):
                            issue = line.lstrip("-*").strip()
                            if issue and issue.lower() != "none":
                                issues.append(issue)

            if "OUTPUT_ANALYSIS:" in response:
                analysis_start = response.find("OUTPUT_ANALYSIS:") + len("OUTPUT_ANALYSIS:")
                output_analysis = response[analysis_start:].strip()
                if output_analysis.lower() == "none":
                    output_analysis = None

        except Exception as e:
            logger.warning("Error parsing evaluation response: {}".format(e))
            is_valid = True
            feedback = "Could not parse evaluation response: {}".format(str(e))

        return EvaluationResult(
            is_valid=is_valid,
            feedback=feedback,
            issues=issues,
            output_analysis=output_analysis
        )


# Global evaluator instance
cell_evaluator = CellOutputEvaluator()
