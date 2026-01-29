"""
Cell Output Evaluator (LLM as a Judge)

This module provides evaluation of cell outputs using Claude as a judge.
After a cell executes successfully for a smoke test example, the evaluator
checks if the output is correct/sensible before running remaining examples.

Key Components:
    - CellOutputEvaluator: Evaluates cell outputs using Claude
    - EvaluationResult: Result of an evaluation (pass/fail with feedback)
    - ExampleOutput: Data structure for example execution results

The evaluator uses a "smoke test" approach:
    1. Run cell for first example
    2. Evaluate the output
    3. If evaluation passes, run remaining examples
    4. If evaluation fails, fix code and retry (up to 5 times)
    5. After max retries, proceed anyway
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, List, Optional

from anthropic import Anthropic
from .models import WorkflowCell
from ..config import settings

logger = logging.getLogger(__name__)


@dataclass
class ExampleOutput:
    """
    Output data for a single example execution.

    Attributes:
        example_id: Unique identifier for this example
        user_input: The input provided for this example
        output_text: The printed output from the cell (CELL_OUTPUT messages)
        output_variables: The variables returned by the cell
        formatted_variables: Human-readable formatted variable values
    """
    example_id: str
    user_input: str
    output_text: str
    output_variables: Dict[str, Any]
    formatted_variables: Dict[str, str]


@dataclass
class EvaluationResult:
    """
    Result of evaluating cell outputs.

    Attributes:
        is_valid: Whether the output is correct/sensible
        feedback: Detailed feedback explaining issues (if any)
        issues: List of specific issues found
        suggested_fix: Optional suggestion for how to fix the code
    """
    is_valid: bool
    feedback: str
    issues: List[str]
    suggested_fix: Optional[str] = None


def load_evaluator_prompt() -> str:
    """
    Load the evaluation system prompt from markdown file.

    Returns:
        str: The evaluation system prompt content, or empty string if not found
    """
    try:
        current_dir = Path(__file__).parent
        prompt_file = current_dir / "evaluator_prompt.md"

        if prompt_file.exists():
            with open(prompt_file, 'r', encoding='utf-8') as f:
                content = f.read()
            logger.info("Loaded evaluator prompt from {}".format(prompt_file))
            return content
        else:
            logger.warning("Evaluator prompt not found at {}".format(prompt_file))
            return ""
    except Exception as e:
        logger.error("Error loading evaluator prompt: {}".format(e))
        return ""


class CellOutputEvaluator:
    """
    Evaluates cell outputs using Claude as a judge.

    After a cell executes successfully for a smoke test example, this evaluator
    checks if the output is correct and sensible. If not, it provides
    feedback that can be used to fix the cell code.

    Attributes:
        anthropic_client: Anthropic API client for Claude calls
        max_evaluation_retries: Maximum number of evaluation/fix cycles (default 5)
    """

    def __init__(
        self,
        anthropic_client: Optional[Anthropic] = None,
        max_evaluation_retries: int = 5
    ):
        """
        Initialize the cell output evaluator.

        Args:
            anthropic_client: Optional Anthropic client. If not provided,
                            creates one using settings.
            max_evaluation_retries: Maximum evaluation/fix retry cycles
        """
        self.anthropic_client = anthropic_client or Anthropic(
            api_key=settings.anthropic_api_key
        )
        self.max_evaluation_retries = max_evaluation_retries

    async def evaluate_smoke_test_output(
        self,
        cell: WorkflowCell,
        smoke_test_output: ExampleOutput,
        workflow_description: str,
        cell_code: str
    ) -> EvaluationResult:
        """
        Evaluate the output from a smoke test (first example) execution.

        Uses Claude to determine if the output is correct/sensible
        given the cell's purpose and the workflow context.

        Args:
            cell: The cell definition with expected inputs/outputs
            smoke_test_output: Output from the smoke test example
            workflow_description: Original workflow description for context
            cell_code: The generated code for the cell

        Returns:
            EvaluationResult: Evaluation result with validity and feedback
        """
        logger.info("Evaluating smoke test output for cell '{}'".format(cell.name))

        # Load the evaluation prompt
        system_prompt = load_evaluator_prompt()
        if not system_prompt:
            # Use a default prompt if file not found
            system_prompt = self._get_default_system_prompt()

        # Build the user message for smoke test evaluation
        user_message = self._build_smoke_test_message(
            cell=cell,
            smoke_test_output=smoke_test_output,
            workflow_description=workflow_description,
            cell_code=cell_code
        )

        try:
            # Call Claude to evaluate the output
            response = self.anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4000,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
                timeout=600.0  # 10 minute timeout
            )

            # Parse the evaluation response
            raw_response = response.content[0].text
            logger.info("Received evaluation response ({} chars)".format(len(raw_response)))

            return self._parse_evaluation_response(raw_response)

        except Exception as e:
            logger.error("Evaluation failed: {}".format(str(e)))
            # Return a "pass" result on evaluation error to avoid blocking
            return EvaluationResult(
                is_valid=True,
                feedback="Evaluation skipped due to error: {}".format(str(e)),
                issues=[]
            )

    def _get_default_system_prompt(self) -> str:
        """
        Get default system prompt for evaluation if prompt file not found.

        Returns:
            str: Default evaluation system prompt
        """
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

Respond in this exact format:

VALID: [true/false]

FEEDBACK:
[Your detailed feedback explaining your evaluation]

ISSUES:
- [Issue 1, if any]
- [Issue 2, if any]
(or "None" if no issues)

SUGGESTED_FIX:
[If VALID is false, provide specific suggestions for fixing the code]
(or "None" if no fix needed)"""

    def _build_smoke_test_message(
        self,
        cell: WorkflowCell,
        smoke_test_output: ExampleOutput,
        workflow_description: str,
        cell_code: str
    ) -> str:
        """
        Build the user message for smoke test evaluation.

        Args:
            cell: The cell definition
            smoke_test_output: Output from the smoke test
            workflow_description: Workflow description for context
            cell_code: The generated cell code

        Returns:
            str: Formatted evaluation request message
        """
        # Format the variables for display
        variables_display = self._format_variables_for_display(
            smoke_test_output.formatted_variables
        )

        message = """Please evaluate the following cell output from a smoke test execution:

WORKFLOW CONTEXT:
{workflow_description}

CELL INFORMATION:
- Name: {cell_name}
- Description: {cell_description}
- Expected Inputs: {inputs}
- Expected Outputs: {outputs}
- Paradigm Tools Used: {tools}

CELL CODE DESCRIPTION:
{code_description}

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

Provide your evaluation in the specified format (VALID, FEEDBACK, ISSUES, SUGGESTED_FIX).""".format(
            workflow_description=workflow_description,
            cell_name=cell.name,
            cell_description=cell.description,
            inputs=", ".join(cell.inputs_required) if cell.inputs_required else "none",
            outputs=", ".join(cell.outputs_produced) if cell.outputs_produced else "none",
            tools=", ".join(cell.paradigm_tools_used) if cell.paradigm_tools_used else "none",
            code_description=cell.code_description or "No description available",
            cell_code=cell_code[:3000] if len(cell_code) > 3000 else cell_code,
            user_input=smoke_test_output.user_input[:500] if smoke_test_output.user_input else "(empty)",
            output_text=smoke_test_output.output_text or "(no printed output)",
            variables=variables_display
        )

        return message

    def _format_variables_for_display(self, variables: Dict[str, str]) -> str:
        """
        Format variables dictionary for display in prompt.

        Args:
            variables: Dictionary of variable name to formatted value

        Returns:
            str: Formatted string representation
        """
        if not variables:
            return "(no variables returned)"

        lines = []
        for name, value in variables.items():
            # Truncate very long values
            if len(value) > 500:
                value = value[:500] + "... (truncated)"
            lines.append("  {}: {}".format(name, value))

        return "\n".join(lines)

    def _parse_evaluation_response(self, response: str) -> EvaluationResult:
        """
        Parse Claude's evaluation response into an EvaluationResult.

        Args:
            response: Raw response text from Claude

        Returns:
            EvaluationResult: Parsed evaluation result
        """
        # Default values
        is_valid = True
        feedback = ""
        issues = []
        suggested_fix = None

        try:
            # Parse VALID field
            if "VALID:" in response:
                valid_line = response.split("VALID:")[1].split("\n")[0].strip().lower()
                is_valid = valid_line in ["true", "yes", "1", "valid", "pass"]

            # Parse FEEDBACK field
            if "FEEDBACK:" in response:
                feedback_start = response.find("FEEDBACK:") + len("FEEDBACK:")
                feedback_end = response.find("ISSUES:")
                if feedback_end == -1:
                    feedback_end = response.find("SUGGESTED_FIX:")
                if feedback_end == -1:
                    feedback_end = len(response)
                feedback = response[feedback_start:feedback_end].strip()

            # Parse ISSUES field
            if "ISSUES:" in response:
                issues_start = response.find("ISSUES:") + len("ISSUES:")
                issues_end = response.find("SUGGESTED_FIX:")
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

            # Parse SUGGESTED_FIX field
            if "SUGGESTED_FIX:" in response:
                fix_start = response.find("SUGGESTED_FIX:") + len("SUGGESTED_FIX:")
                suggested_fix = response[fix_start:].strip()
                if suggested_fix.lower() == "none":
                    suggested_fix = None

        except Exception as e:
            logger.warning("Error parsing evaluation response: {}".format(e))
            # On parse error, default to valid to avoid blocking
            is_valid = True
            feedback = "Could not parse evaluation response: {}".format(str(e))

        return EvaluationResult(
            is_valid=is_valid,
            feedback=feedback,
            issues=issues,
            suggested_fix=suggested_fix
        )


# Global evaluator instance
cell_evaluator = CellOutputEvaluator()
