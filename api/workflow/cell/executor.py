"""Cell-based workflow executor with parallel layer support and LLM evaluation."""

import asyncio
import io
import json
import logging
import time
import re
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime
from typing import Optional, Dict, Any, List, AsyncGenerator, Tuple
from dataclasses import dataclass

from ..models import WorkflowCell, WorkflowPlan, CellStatus
from .generator import CellCodeGenerator
from .evaluator import CellOutputEvaluator, ExampleOutput, EvaluationResult
from ...config import settings
from ...paradigm_client import ParadigmClient, _extract_v3_answer


@dataclass
class CellExecutionResult:
    """Result of executing a single cell with full retry/evaluation cycle."""
    cell: WorkflowCell
    success: bool
    output: str = ""
    output_variables: Dict[str, Any] = None
    events: List[Dict[str, Any]] = None
    error: Optional[str] = None
    attempts: int = 1

    def __post_init__(self):
        if self.output_variables is None:
            self.output_variables = {}
        if self.events is None:
            self.events = []

logger = logging.getLogger(__name__)


class CellExecutor:
    """Executes workflow cells with state passing and real-time event streaming."""

    def __init__(self, paradigm_api_key: str = None, agent_id: int = None, available_tools=None):
        self.max_cell_execution_time = settings.max_cell_execution_time
        self.max_retry_attempts = settings.max_retry_attempts
        self.max_evaluation_retries = settings.max_evaluation_retries
        self.min_eval_score_to_proceed = settings.min_evaluation_score_to_proceed
        self.paradigm_api_key = paradigm_api_key or settings.lighton_api_key
        self.agent_id = agent_id  # Paradigm agent ID (preferred over chat_setting_id)
        self.available_tools = available_tools  # Discovered tools for cell generator
        self.cell_generator = CellCodeGenerator()
        self.cell_evaluator = CellOutputEvaluator()

    def _format_output_variables(self, variables: Dict[str, Any]) -> Dict[str, str]:
        """Format output variables for UI display, showing full content without truncation."""
        import json

        formatted = {}
        for key, value in variables.items():
            if key in ["LIGHTON_API_KEY", "PARADIGM_API_KEY", "user_input", "attached_file_ids"]:
                continue

            if isinstance(value, (dict, list)):
                formatted[key] = json.dumps(value, indent=2, ensure_ascii=False)
            elif isinstance(value, str):
                formatted[key] = value
            else:
                formatted[key] = str(value)

        return formatted

    def _summarize_dict_structure(self, d: dict, depth: int = 0, max_depth: int = 3) -> str:
        """Recursively summarize dict key structure with types and previews for LLM context."""
        if depth >= max_depth:
            return "{...}"
        parts = []
        indent = "  " * (depth + 1)
        for k, v in d.items():
            if isinstance(v, dict):
                nested = self._summarize_dict_structure(v, depth + 1, max_depth)
                parts.append("{}{} (dict): {}".format(indent, k, nested))
            elif isinstance(v, list):
                if v and isinstance(v[0], dict):
                    parts.append("{}{} (list of {} dicts)".format(indent, k, len(v)))
                else:
                    parts.append("{}{} (list, {} items)".format(indent, k, len(v)))
            elif isinstance(v, str):
                preview = v[:120]
                if len(v) > 120:
                    preview += "..."
                parts.append("{}{} (str): {}".format(indent, k, preview))
            else:
                parts.append("{}{}: {}".format(indent, k, str(v)[:80]))
        return "{{{}}}".format("\n" + "\n".join(parts) + "\n" + "  " * depth) if parts else "{}"

    def _load_cell_generation_guidance(self) -> str:
        """Load critical sections from the cell generation prompt."""
        try:
            from pathlib import Path
            prompt_file = Path(__file__).parent.parent / "prompts" / "cell.md"

            if not prompt_file.exists():
                logger.warning("Cell prompt file not found")
                return ""

            with open(prompt_file, 'r', encoding='utf-8') as f:
                full_prompt = f.read()

            # Extract key sections
            sections_to_include = []

            # Extract MODEL ROBUSTNESS section
            if "### ⚠️ CRITICAL: MODEL ROBUSTNESS" in full_prompt:
                start = full_prompt.find("### ⚠️ CRITICAL: MODEL ROBUSTNESS")
                end = full_prompt.find("### 🚨 CRITICAL: Choosing the Right Method", start)
                if end > start:
                    sections_to_include.append(full_prompt[start:end].strip())

            # Extract REMEMBER rules
            if "## REMEMBER" in full_prompt:
                start = full_prompt.find("## REMEMBER")
                # Get everything after REMEMBER (it's at the end)
                sections_to_include.append(full_prompt[start:].strip())

            return "\n\n".join(sections_to_include)
        except Exception as e:
            logger.error("Failed to load cell generation guidance: {}".format(e))
            return ""

    def _extract_return_hints(self, code: str, outputs_produced: List[str]) -> Dict[str, str]:
        """Extract return statement from generated code to hint output format to consumer cells."""
        match = re.search(r'return\s*\{', code)
        if not match:
            return {}

        start = match.start()
        brace_start = match.end() - 1
        depth = 0
        i = brace_start
        while i < len(code):
            ch = code[i]
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return_stmt = code[start:i + 1]
                    hints = {}
                    for var_name in outputs_produced:
                        if var_name in return_stmt:
                            hints[var_name] = return_stmt
                    return hints
            elif ch in ('"', "'"):
                quote = ch
                i += 1
                while i < len(code) and code[i] != quote:
                    if code[i] == '\\':
                        i += 1
                    i += 1
            i += 1

        return {}

    async def fix_cell_code(
        self,
        cell: WorkflowCell,
        failed_code: str,
        error_message: str,
        execution_context: Dict[str, Any],
        workflow_description: str,
        attempt_number: int,
        output_example: Optional[str] = None,
        is_final_cell: bool = False
    ) -> str:
        """Use Claude to fix failed cell code based on error message."""
        logger.info("Attempting to fix cell '{}' (attempt {}/{})".format(
            cell.name, attempt_number, self.max_retry_attempts
        ))

        from ..prompts.loader import PromptLoader
        full_cell_prompt = PromptLoader.load("cell")

        logger.info("Loaded {} chars of full cell prompt for fix".format(len(full_cell_prompt)))

        # Show full dict/list structure so report/aggregation cells know available keys
        context_summary = []
        for key, value in execution_context.items():
            if key in ["LIGHTON_API_KEY", "PARADIGM_API_KEY"]:
                continue
            if isinstance(value, dict):
                value_str = self._summarize_dict_structure(value)
                context_summary.append("  - {} (dict): {}".format(key, value_str))
            elif isinstance(value, list):
                if value:
                    first_item = str(value[0])[:80]
                    value_str = "list of {} items, first: {}".format(len(value), first_item)
                else:
                    value_str = "empty list"
                context_summary.append("  - {} (list): {}".format(key, value_str))
            elif isinstance(value, str):
                value_str = value[:500]
                if len(value) > 500:
                    value_str += "... ({} chars total)".format(len(value))
                context_summary.append("  - {} (str): {}".format(key, value_str))
            else:
                context_summary.append("  - {}: {}".format(key, str(value)[:200]))

        context_info = "\n".join(context_summary) if context_summary else "  (none yet)"

        fix_prompt = """You are debugging Python code that failed during execution. Fix the code to make it work correctly.

FULL CELL GENERATION PROMPT (ALL GUIDELINES):
{full_cell_prompt}

WORKFLOW CONTEXT:
{workflow_description}

CELL INFORMATION:
- Cell Name: {cell_name}
- Cell Description: {cell_description}
- Step Number: {step_number}
- Expected Inputs: {inputs}
- Expected Outputs: {outputs}""".format(
            full_cell_prompt=full_cell_prompt,
            workflow_description=workflow_description,
            cell_name=cell.name,
            cell_description=cell.description,
            step_number=cell.step_number,
            inputs=", ".join(cell.inputs_required) if cell.inputs_required else "none",
            outputs=", ".join(cell.outputs_produced) if cell.outputs_produced else "none"
        )

        if cell.success_criteria:
            fix_prompt += """

CELL-SPECIFIC SUCCESS CRITERIA:
{criteria}

Your fixed code MUST produce output that meets these specific requirements.""".format(
                criteria=cell.success_criteria
            )

        if output_example and is_final_cell:
            fix_prompt += """

OUTPUT FORMAT EXAMPLE (FINAL CELL):
The user expects output in this FORMAT:
```
{example}
```

Your fixed code should produce output with similar format/structure.""".format(
                example=output_example
            )

        fix_prompt += """

CURRENT EXECUTION CONTEXT (available variables):
{context_info}

FAILED CODE:
```python
{failed_code}
```

ERROR MESSAGE:
{error_message}

DEBUGGING INSTRUCTIONS:
1. First, check the FULL CELL GENERATION PROMPT above - especially critical guidelines and model robustness rules
2. Analyze the error carefully - what went wrong?
3. If the error is about model not found or invalid model:
   - NEVER use model versions like "alfred-40b-1123", "llama-3.1-70b", etc.
   - Either OMIT the model parameter entirely, OR use "alfred-ft5"
4. Check if required inputs are available in the context
5. Fix any syntax errors, logic errors, or API usage issues
6. Ensure the code returns the expected outputs
7. Make sure to handle edge cases (empty lists, None values, etc.)
8. Use print("CELL_OUTPUT: ...") for progress updates
9. Keep the same function signature: async def execute_cell(context: Dict[str, Any]) -> Dict[str, Any]

Generate ONLY the corrected Python code - no markdown, no explanations.
The code must be complete and executable.
""".format(
            context_info=context_info,
            failed_code=failed_code,
            error_message=error_message
        )

        # Reuse existing Anthropic client instead of creating a new one per fix call
        anthropic_client = self.cell_generator.anthropic_client

        system_prompt = """You are an expert Python debugger specializing in fixing workflow automation code.

CRITICAL RULES YOU MUST FOLLOW:
1. Generate ONLY executable Python code - no markdown, no explanations
2. STRICTLY follow the CRITICAL CODING GUIDELINES provided in the prompt
3. For Paradigm API model errors: ONLY use "alfred-ft5" or omit model parameter entirely
4. NEVER invent or hallucinate model names (no llama, no meta-llama, no gpt models)
5. Use the exact ParadigmClient method signatures from the guidelines
6. Follow all formatting rules from the REMEMBER section

Your fix MUST be syntactically correct and follow all the coding guidelines exactly."""

        response = anthropic_client.messages.create(
            model=settings.anthropic_model,
            max_tokens=settings.anthropic_max_tokens_plan,
            system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": fix_prompt}],
            timeout=settings.anthropic_timeout
        )

        fixed_code = response.content[0].text
        fixed_code = self.cell_generator._extract_code(fixed_code)

        logger.info("Generated fixed code for cell '{}' ({} chars)".format(
            cell.name, len(fixed_code)
        ))

        return fixed_code

    def _build_examples_section_for_fix(
        self,
        all_example_results: List[Dict[str, Any]]
    ) -> str:
        """Build formatted examples section showing all inputs/outputs for the fix prompt."""
        if not all_example_results:
            return "(no example results)"

        examples_text = ""
        max_output_length = 1000  # Per-example output limit
        max_total_length = 6000  # Total examples section limit

        for idx, result in enumerate(all_example_results, 1):
            user_input = result.get("user_input", "(unknown)")
            output_text = result.get("output", "(no output)")
            variables = result.get("variables", {})
            formatted_vars = result.get("formatted_variables", {})
            success = result.get("success", False)

            if len(output_text) > max_output_length:
                output_text = output_text[:max_output_length] + "... (truncated)"

            vars_display = ""
            if formatted_vars:
                for var_name, var_value in formatted_vars.items():
                    var_str = str(var_value)
                    if len(var_str) > 300:
                        var_str = var_str[:300] + "... (truncated)"
                    vars_display += "    {}: {}\n".format(var_name, var_str)
            elif variables:
                for var_name, var_value in variables.items():
                    var_str = str(var_value)
                    if len(var_str) > 300:
                        var_str = var_str[:300] + "... (truncated)"
                    vars_display += "    {}: {}\n".format(var_name, var_str)
            else:
                vars_display = "    (no variables returned)\n"

            example_section = """
EXAMPLE {idx}: {status}
  User Input: {user_input}
  Printed Output:
{output_text}
  Output Variables:
{vars_display}
""".format(
                idx=idx,
                status="SUCCESS" if success else "FAILED",
                user_input=str(user_input)[:300] if user_input else "(empty)",
                output_text=output_text,
                vars_display=vars_display
            )

            if len(examples_text) + len(example_section) > max_total_length:
                examples_text += "\n... ({} more examples truncated due to length)\n".format(
                    len(all_example_results) - idx + 1
                )
                break

            examples_text += example_section

        return examples_text

    def _build_evaluation_history_section(self, evaluation_history: Optional[List[Dict[str, Any]]]) -> str:
        """Build a section summarizing previous evaluation attempts for feedback accumulation."""
        if not evaluation_history or len(evaluation_history) <= 1:
            return ""

        # Only include previous attempts (not the current one which is already in the main feedback)
        previous = evaluation_history[:-1]
        if not previous:
            return ""

        lines = [
            "\nPREVIOUS EVALUATION ATTEMPTS ({} prior attempts):".format(len(previous)),
            "Review what was tried before and what feedback was given. Use this to inform your fix."
        ]
        for entry in previous:
            attempt = entry.get("attempt", "?")
            score = entry.get("score", "N/A")
            feedback = entry.get("feedback", "No feedback")
            issues = entry.get("issues", [])
            lines.append("\n--- Attempt {} (score: {}) ---".format(attempt, score))
            lines.append("Feedback: {}".format(feedback[:500]))
            if issues:
                lines.append("Issues: {}".format("; ".join(str(i) for i in issues[:5])))

        lines.append("\nIf the same issues persist, consider a different approach. If the issue is a small bug, a targeted fix is fine.\n")
        return "\n".join(lines)

    async def fix_cell_code_from_evaluation(
        self,
        cell: WorkflowCell,
        current_code: str,
        evaluation_result: EvaluationResult,
        all_example_results: List[Dict[str, Any]],
        workflow_description: str,
        attempt_number: int,
        output_example: Optional[str] = None,
        evaluation_history: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """Use Claude to fix cell code based on evaluation feedback from all examples."""
        logger.info("Fixing cell '{}' based on evaluation feedback (attempt {}/{})".format(
            cell.name, attempt_number, self.max_evaluation_retries
        ))

        from ..prompts.loader import PromptLoader
        full_cell_prompt = PromptLoader.load("cell")

        examples_section = self._build_examples_section_for_fix(all_example_results)

        issues_text = "\n".join("- {}".format(issue) for issue in evaluation_result.issues) if evaluation_result.issues else "No specific issues listed"

        fix_prompt = """You are fixing Python code that executed successfully but produced INCORRECT or INVALID output.
The code runs without errors, but the output doesn't meet expectations based on evaluation.

FULL CELL GENERATION PROMPT (ALL GUIDELINES):
{full_cell_prompt}

WORKFLOW CONTEXT:
{workflow_description}

CELL INFORMATION:
- Cell Name: {cell_name}
- Cell Description: {cell_description}
- Step Number: {step_number}
- Expected Inputs: {inputs}
- Expected Outputs: {outputs}""".format(
            full_cell_prompt=full_cell_prompt,
            workflow_description=workflow_description,
            cell_name=cell.name,
            cell_description=cell.description,
            step_number=cell.step_number,
            inputs=", ".join(cell.inputs_required) if cell.inputs_required else "none",
            outputs=", ".join(cell.outputs_produced) if cell.outputs_produced else "none"
        )

        if cell.success_criteria:
            fix_prompt += """

CELL-SPECIFIC SUCCESS CRITERIA:
{criteria}

Your fixed code MUST produce output that meets these specific requirements.""".format(
                criteria=cell.success_criteria
            )

        if output_example:
            fix_prompt += """

OUTPUT FORMAT EXAMPLE (FINAL CELL):
The user expects output in this FORMAT:
```
{example}
```

Your fixed code should produce output with similar format/structure.""".format(
                example=output_example
            )

        fix_prompt += """

CURRENT CODE (executes but produces wrong output):
```python
{current_code}
```

=== ALL EXAMPLE OUTPUTS ({num_examples} examples) ===
{examples_section}
=== END OF EXAMPLES ===

EVALUATION FEEDBACK:
{feedback}

SPECIFIC ISSUES FOUND:
{issues}

OUTPUT ANALYSIS FROM EVALUATOR:
{output_analysis}

The evaluator identified these OUTPUT problems. Your job is to fix the CODE to produce correct OUTPUT.
{history_section}
FIX INSTRUCTIONS:
1. The code RUNS without errors, but produces incorrect/invalid OUTPUT
2. Review ALL example outputs above to identify PATTERNS in the issues
3. Focus on fixing problems that affect multiple examples
4. Common issues include:
   - Wrong data structure returned
   - Missing fields in output
   - Incorrect parsing of API responses
   - Data not being extracted correctly
   - Edge cases not handled properly
5. Keep the same function signature: async def execute_cell(context: Dict[str, Any]) -> Dict[str, Any]
6. Use print("CELL_OUTPUT: ...") for progress updates

Generate ONLY the corrected Python code - no markdown, no explanations.
The code must be complete and executable.
""".format(
            current_code=current_code,
            num_examples=len(all_example_results),
            examples_section=examples_section,
            feedback=evaluation_result.feedback,
            issues=issues_text,
            output_analysis=evaluation_result.output_analysis or "No specific analysis provided",
            history_section=self._build_evaluation_history_section(evaluation_history)
        )

        # Reuse existing Anthropic client instead of creating a new one per fix call
        anthropic_client = self.cell_generator.anthropic_client

        system_prompt = """You are an expert Python developer fixing workflow automation code.

The code executes without runtime errors, but produces INCORRECT OUTPUT based on evaluation.

CRITICAL RULES:
1. Generate ONLY executable Python code - no markdown, no explanations
2. Follow the CRITICAL CODING GUIDELINES provided
3. Focus on fixing the OUTPUT issues, not runtime errors
4. The code must return the correct data structure and values
5. Use proper API response parsing
6. Follow all formatting rules from the REMEMBER section"""

        response = anthropic_client.messages.create(
            model=settings.anthropic_model,
            max_tokens=settings.anthropic_max_tokens_plan,
            system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": fix_prompt}],
            timeout=settings.anthropic_timeout
        )

        fixed_code = response.content[0].text
        fixed_code = self.cell_generator._extract_code(fixed_code)

        logger.info("Generated evaluation-fixed code for cell '{}' ({} chars)".format(
            cell.name, len(fixed_code)
        ))

        return fixed_code

    async def execute_workflow_stepwise(
        self,
        plan: WorkflowPlan,
        user_input: str,
        attached_file_ids: Optional[List[int]] = None,
        workflow_description: str = ""
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute workflow cell by cell, yielding SSE-compatible events for real-time streaming."""
        execution_context: Dict[str, Any] = {
            "user_input": user_input,
            "attached_file_ids": attached_file_ids or []
        }

        total_cells = len(plan.cells)
        completed_cells = 0

        # Track return hints from producer cells for downstream consumer cells
        producer_return_hints: Dict[str, str] = {}

        logger.info("Starting stepwise execution with {} cells".format(total_cells))

        yield {
            "type": "workflow_start",
            "total_cells": total_cells,
            "timestamp": datetime.utcnow().isoformat()
        }

        for cell in plan.cells:
            attempt = 0
            cell_succeeded = False
            last_error = None

            while attempt < self.max_retry_attempts and not cell_succeeded:
                attempt += 1
                is_retry = attempt > 1

                try:
                    if cell.status == CellStatus.PENDING or is_retry:
                        cell.mark_generating()

                        yield {
                            "type": "cell_generating",
                            "cell_id": cell.id,
                            "cell_name": cell.name,
                            "step_number": cell.step_number,
                            "description": cell.description,
                            "attempt": attempt,
                            "is_retry": is_retry,
                            "timestamp": datetime.utcnow().isoformat()
                        }

                        if is_retry:
                            logger.info("🔄 Retrying cell '{}' (attempt {}/{})".format(
                                cell.name, attempt, self.max_retry_attempts
                            ))
                            yield {
                                "type": "cell_retrying",
                                "cell_id": cell.id,
                                "cell_name": cell.name,
                                "attempt": attempt,
                                "max_attempts": self.max_retry_attempts,
                                "previous_error": last_error,
                                "timestamp": datetime.utcnow().isoformat()
                            }

                            code = await self.fix_cell_code(
                                cell=cell,
                                failed_code=cell.generated_code,
                                error_message=last_error,
                                execution_context=execution_context,
                                workflow_description=workflow_description,
                                attempt_number=attempt,
                                output_example=plan.output_example if hasattr(plan, 'output_example') else None,
                                is_final_cell=(cell.step_number == total_cells)
                            )
                        else:
                            code = await self.cell_generator.generate_cell_code(
                                cell=cell,
                                available_context=plan.shared_context_schema,
                                workflow_description=workflow_description,
                                producer_return_hints=producer_return_hints,
                                available_tools=self.available_tools
                            )

                        cell.mark_ready(code, cell.description)

                        new_hints = self._extract_return_hints(code, cell.outputs_produced)
                        producer_return_hints.update(new_hints)

                        yield {
                            "type": "cell_ready",
                            "cell_id": cell.id,
                            "cell_name": cell.name,
                            "code_preview": code[:300] + "..." if len(code) > 300 else code,
                            "full_code": code,
                            "code_description": cell.description,
                            "success_criteria": cell.success_criteria,
                            "attempt": attempt,
                            "is_retry": is_retry,
                            "timestamp": datetime.utcnow().isoformat()
                        }

                    cell.mark_executing()

                    yield {
                        "type": "cell_executing",
                        "cell_id": cell.id,
                        "cell_name": cell.name,
                        "step_number": cell.step_number,
                        "attempt": attempt,
                        "timestamp": datetime.utcnow().isoformat()
                    }

                    for required_input in cell.inputs_required:
                        if required_input not in execution_context:
                            logger.warning(
                                "MISSING INPUT: Cell '{}' requires '{}' but it's not in context. "
                                "Available keys: {}".format(
                                    cell.name, required_input,
                                    list(execution_context.keys())
                                )
                            )
                        elif execution_context[required_input] is None:
                            logger.warning(
                                "NULL INPUT: Cell '{}' input '{}' is None".format(
                                    cell.name, required_input
                                )
                            )

                    start_time = time.time()
                    cell_result = await self._execute_cell_code(
                        cell.generated_code,
                        execution_context,
                        cell.id
                    )
                    execution_time = time.time() - start_time

                    output_variables = cell_result.get("variables", {})
                    execution_context.update(output_variables)

                    from ..core.executor import workflow_executor
                    workflow_executor.store_execution_context(plan.workflow_id, execution_context)

                    formatted_outputs = self._format_output_variables(output_variables)

                    cell.mark_completed(
                        output=cell_result.get("output", ""),
                        variables=output_variables,
                        execution_time=execution_time
                    )

                    completed_cells += 1
                    cell_succeeded = True

                    yield {
                        "type": "cell_completed",
                        "cell_id": cell.id,
                        "cell_name": cell.name,
                        "step_number": cell.step_number,
                        "output": cell_result.get("output", ""),
                        "variables": list(output_variables.keys()),
                        "variable_values": formatted_outputs,
                        "execution_time": execution_time,
                        "attempt": attempt,
                        "was_retried": attempt > 1,
                        "timestamp": datetime.utcnow().isoformat()
                    }

                except asyncio.TimeoutError:
                    error_msg = "Cell timed out after {}s".format(self.max_cell_execution_time)
                    last_error = error_msg

                    logger.warning("⏱️ Cell '{}' timed out (attempt {}/{})".format(
                        cell.name, attempt, self.max_retry_attempts
                    ))

                    if attempt >= self.max_retry_attempts:
                        cell.mark_failed(error_msg)

                        yield {
                            "type": "cell_failed",
                            "cell_id": cell.id,
                            "cell_name": cell.name,
                            "step_number": cell.step_number,
                            "error": error_msg,
                            "attempts_made": attempt,
                            "timestamp": datetime.utcnow().isoformat()
                        }

                        yield {
                            "type": "workflow_failed",
                            "error": "Cell '{}' timed out after {} attempts".format(cell.name, attempt),
                            "completed_cells": completed_cells,
                            "timestamp": datetime.utcnow().isoformat()
                        }
                        return

                except Exception as e:
                    import traceback
                    error_msg = str(e)
                    full_traceback = traceback.format_exc()
                    last_error = "Error: {}\n\nTraceback:\n{}".format(error_msg, full_traceback)

                    logger.warning("❌ Cell '{}' failed (attempt {}/{}): {}".format(
                        cell.name, attempt, self.max_retry_attempts, error_msg
                    ))

                    if attempt >= self.max_retry_attempts:
                        cell.mark_failed(error_msg)

                        logger.error("Cell '{}' failed after {} attempts: {}".format(
                            cell.name, attempt, error_msg
                        ))

                        yield {
                            "type": "cell_failed",
                            "cell_id": cell.id,
                            "cell_name": cell.name,
                            "step_number": cell.step_number,
                            "error": error_msg,
                            "attempts_made": attempt,
                            "timestamp": datetime.utcnow().isoformat()
                        }

                        yield {
                            "type": "workflow_failed",
                            "error": "Cell '{}' failed after {} attempts: {}".format(
                                cell.name, attempt, error_msg
                            ),
                            "completed_cells": completed_cells,
                            "timestamp": datetime.utcnow().isoformat()
                        }
                        return

        # All cells completed
        final_result = execution_context.get("final_result", "Workflow completed successfully")

        yield {
            "type": "workflow_completed",
            "final_result": final_result,
            "total_cells": total_cells,
            "completed_cells": completed_cells,
            "timestamp": datetime.utcnow().isoformat()
        }

    async def _execute_cell_code(
        self,
        code: str,
        context: Dict[str, Any],
        cell_id: str
    ) -> Dict[str, Any]:
        """Execute a single cell's code with the given context and return output + variables."""
        code = self._inject_api_keys(code)
        execution_globals = self._create_execution_environment()
        output_lines: List[str] = []

        # Custom print that captures CELL_OUTPUT messages for the UI
        original_print = print

        def capture_print(*args, sep=' ', end='\n', file=None, flush=False):
            message = sep.join(str(arg) for arg in args)

            if "CELL_OUTPUT:" in message:
                output_lines.append(message.replace("CELL_OUTPUT:", "").strip())

            original_print(*args, sep=sep, end=end, file=file, flush=flush)

        execution_globals['print'] = capture_print

        try:
            compiled_code = compile(code, '<cell>', 'exec')

            result = await asyncio.wait_for(
                self._run_cell_code(compiled_code, execution_globals, context),
                timeout=self.max_cell_execution_time
            )

            output = "\n".join(output_lines) if output_lines else ""

            return {
                "output": output,
                "variables": result
            }

        except asyncio.TimeoutError:
            raise asyncio.TimeoutError(
                "Cell execution timed out after {}s".format(self.max_cell_execution_time)
            )
        except Exception as e:
            raise Exception("Cell execution failed: {}".format(str(e)))
        finally:
            execution_globals['print'] = original_print

    async def _run_cell_code(
        self,
        compiled_code,
        execution_globals: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Run compiled cell code and return output variables."""
        stderr_capture = io.StringIO()

        try:
            with redirect_stderr(stderr_capture):
                exec(compiled_code, execution_globals)

                if 'execute_cell' not in execution_globals:
                    raise Exception("execute_cell function not found in generated code")

                cell_func = execution_globals['execute_cell']

                if asyncio.iscoroutinefunction(cell_func):
                    result = await cell_func(context)
                else:
                    result = cell_func(context)

                if not isinstance(result, dict):
                    result = {"final_result": str(result)}

                return result

        except Exception as e:
            stderr_content = stderr_capture.getvalue()
            if stderr_content:
                raise Exception("{}\nStderr: {}".format(str(e), stderr_content))
            raise

    def _inject_api_keys(self, code: str) -> str:
        """Replace placeholder config values in generated code.

        API keys are NOT injected into source code — they are passed via
        execution globals (see _build_exec_globals). This prevents keys from
        appearing in code previews, logs, or exported packages.
        Only base URL and non-secret config values are replaced here.
        """
        # Remove API key placeholders — the real key is available at runtime
        # via the LIGHTON_API_KEY execution global
        code = code.replace(
            'LIGHTON_API_KEY = os.getenv("PARADIGM_API_KEY", "your_api_key_here")',
            '# LIGHTON_API_KEY is injected at runtime via execution context'
        )
        code = code.replace(
            'LIGHTON_API_KEY = "your_api_key_here"',
            '# LIGHTON_API_KEY is injected at runtime via execution context'
        )
        code = code.replace(
            'LIGHTON_BASE_URL = os.getenv("PARADIGM_BASE_URL", "https://paradigm.lighton.ai")',
            'LIGHTON_BASE_URL = "{}"'.format(settings.lighton_base_url)
        )

        return code

    # Modules that generated cell code is allowed to import
    ALLOWED_IMPORT_MODULES = {
        # Standard library — safe utilities
        "asyncio", "json", "re", "math", "datetime", "time", "logging",
        "collections", "itertools", "functools", "copy", "string",
        "decimal", "fractions", "statistics", "textwrap", "difflib",
        "hashlib", "hmac", "base64", "urllib", "urllib.parse",
        "html", "xml", "csv", "io", "uuid", "enum", "dataclasses",
        "typing", "types", "abc", "contextlib", "traceback",
        # Network — needed for external API calls in workflows
        "aiohttp", "httpx",
        # Data — common data processing libraries
        "pydantic",
    }

    def _create_execution_environment(self) -> Dict[str, Any]:
        """Create execution environment with builtins, ParadigmClient, and API config pre-injected."""
        # Restricted __import__ that only allows whitelisted modules
        _real_import = __import__
        allowed = self.ALLOWED_IMPORT_MODULES

        def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
            # Allow relative imports (level > 0) — these resolve within already-loaded packages
            if level > 0:
                return _real_import(name, globals, locals, fromlist, level)
            # Check top-level module name against whitelist
            top_module = name.split(".")[0]
            if top_module not in allowed:
                raise ImportError(
                    "Module '{}' is not allowed in the execution sandbox. "
                    "Allowed modules: {}".format(name, ", ".join(sorted(allowed)))
                )
            return _real_import(name, globals, locals, fromlist, level)

        return {
            '__name__': '__main__',
            '__builtins__': {
                'len': len, 'str': str, 'int': int, 'float': float, 'bool': bool,
                'list': list, 'dict': dict, 'tuple': tuple, 'set': set,
                'range': range, 'enumerate': enumerate, 'zip': zip,
                'sorted': sorted, 'reversed': reversed,
                'sum': sum, 'min': min, 'max': max, 'abs': abs, 'round': round,
                'isinstance': isinstance, 'hasattr': hasattr, 'getattr': getattr,
                'setattr': setattr, 'type': type,
                'ValueError': ValueError, 'TypeError': TypeError,
                'Exception': Exception, 'RuntimeError': RuntimeError,
                'NameError': NameError, 'ImportError': ImportError,
                '__import__': _safe_import,
                'any': any, 'all': all, 'globals': globals, 'print': print,
                '__build_class__': __build_class__, 'object': object, 'super': super,
                'property': property, 'staticmethod': staticmethod,
                'classmethod': classmethod,
                'bytes': bytes, 'bytearray': bytearray,
                'iter': iter, 'next': next, 'slice': slice,
                'map': map, 'filter': filter,
                'vars': vars, 'dir': dir, 'id': id, 'hash': hash,
                'ord': ord, 'chr': chr, 'bin': bin, 'oct': oct, 'hex': hex,
                'divmod': divmod, 'pow': pow, 'callable': callable,
            },
            'ParadigmClient': ParadigmClient,
            'LIGHTON_API_KEY': self.paradigm_api_key,
            'LIGHTON_BASE_URL': settings.lighton_base_url,
            'LIGHTON_AGENT_ID': self.agent_id,
            '_extract_v3_answer': _extract_v3_answer,
            # Pre-injected typing symbols so generated code doesn't crash on annotations
            'Dict': Dict,
            'Any': Any,
            'List': List,
            'Optional': Optional,
            'Tuple': Tuple,
        }

    async def execute_workflow_with_evaluation(
        self,
        plan: WorkflowPlan,
        examples: List[Dict[str, Any]],
        workflow_description: str = ""
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute workflow with layer-based parallelization and smoke test evaluation."""
        if not examples:
            yield {
                "type": "error",
                "error": "No examples provided for execution",
                "timestamp": datetime.utcnow().isoformat()
            }
            return

        total_cells = len(plan.cells)
        total_examples = len(examples)

        layers = plan.get_cells_by_layer()
        total_layers = len(layers)
        is_parallel = plan.is_parallel_workflow()

        logger.info("Starting execution with evaluation: {} cells, {} examples, {} layers (parallel={})".format(
            total_cells, total_examples, total_layers, is_parallel
        ))

        yield {
            "type": "workflow_start",
            "total_cells": total_cells,
            "total_examples": total_examples,
            "total_layers": total_layers,
            "is_parallel": is_parallel,
            "evaluation_enabled": True,
            "timestamp": datetime.utcnow().isoformat()
        }

        # Each example has its own context flow, updated as layers complete
        example_contexts: List[Dict[str, Any]] = []
        for i, example in enumerate(examples):
            example_contexts.append({
                "user_input": example.get("user_input", ""),
                "attached_file_ids": example.get("attached_file_ids", [])
            })

        completed_cells = 0

        for layer_num in sorted(layers.keys()):
            layer_cells = layers[layer_num]
            is_parallel_layer = len(layer_cells) > 1

            yield {
                "type": "layer_started",
                "layer": layer_num,
                "cell_count": len(layer_cells),
                "cells": [{"id": c.id, "name": c.name, "display_step": c.get_display_step()} for c in layer_cells],
                "parallel": is_parallel_layer,
                "timestamp": datetime.utcnow().isoformat()
            }

            event_queue: asyncio.Queue = asyncio.Queue()

            layer_task = asyncio.create_task(
                self._execute_layer_with_examples(
                    layer_cells=layer_cells,
                    examples=examples,
                    example_contexts=example_contexts,
                    workflow_description=workflow_description,
                    plan=plan,
                    event_queue=event_queue
                )
            )

            while not layer_task.done():
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=0.1)
                    yield event
                except asyncio.TimeoutError:
                    continue

            layer_results = await layer_task

            while not event_queue.empty():
                event = event_queue.get_nowait()
                yield event

            for result in layer_results:
                if result.get("success"):
                    cell_outputs = result.get("example_outputs", {})
                    for ex_idx, outputs in cell_outputs.items():
                        if ex_idx < len(example_contexts):
                            example_contexts[ex_idx].update(outputs)

            all_succeeded = all(r.get("success", False) for r in layer_results)
            failed_cells = [r["cell"].name for r in layer_results if not r.get("success")]

            if not all_succeeded:
                yield {
                    "type": "layer_failed",
                    "layer": layer_num,
                    "failed_cells": failed_cells,
                    "timestamp": datetime.utcnow().isoformat()
                }

                yield {
                    "type": "workflow_failed",
                    "error": "Layer {} failed: cells {} did not complete".format(layer_num, failed_cells),
                    "completed_cells": completed_cells,
                    "failed_layer": layer_num,
                    "timestamp": datetime.utcnow().isoformat()
                }
                return

            completed_cells += len(layer_cells)

            yield {
                "type": "layer_completed",
                "layer": layer_num,
                "cell_count": len(layer_cells),
                "all_passed": True,
                "timestamp": datetime.utcnow().isoformat()
            }

        yield {
            "type": "workflow_completed",
            "total_cells": total_cells,
            "completed_cells": completed_cells,
            "total_examples": total_examples,
            "total_layers": total_layers,
            "timestamp": datetime.utcnow().isoformat()
        }

    async def _execute_layer_with_examples(
        self,
        layer_cells: List[WorkflowCell],
        examples: List[Dict[str, Any]],
        example_contexts: List[Dict[str, Any]],
        workflow_description: str,
        plan: WorkflowPlan,
        event_queue: asyncio.Queue
    ) -> List[Dict[str, Any]]:
        """Execute all cells in a layer in parallel, streaming events via event_queue."""
        if not layer_cells:
            return []

        tasks = [
            self._execute_cell_with_all_examples_streaming(
                cell=cell,
                examples=examples,
                example_contexts=[ctx.copy() for ctx in example_contexts],
                workflow_description=workflow_description,
                plan=plan,
                event_queue=event_queue
            )
            for cell in layer_cells
        ]

        results = await asyncio.gather(*tasks)
        return list(results)

    async def _execute_cell_with_all_examples(
        self,
        cell: WorkflowCell,
        examples: List[Dict[str, Any]],
        example_contexts: List[Dict[str, Any]],
        workflow_description: str,
        plan: WorkflowPlan
    ) -> Dict[str, Any]:
        """Execute a single cell with smoke test, LLM evaluation, retry cycle, then remaining examples."""
        events: List[Dict[str, Any]] = []
        cell_code = None
        example_outputs: Dict[int, Dict[str, Any]] = {}  # example_idx -> outputs
        total_examples = len(examples)

        cell.mark_generating()
        events.append({
            "type": "cell_generating",
            "cell_id": cell.id,
            "cell_name": cell.name,
            "step_number": cell.step_number,
            "layer": cell.layer,
            "display_step": cell.get_display_step(),
            "description": cell.description,
            "timestamp": datetime.utcnow().isoformat()
        })

        try:
            code = await self.cell_generator.generate_cell_code(
                cell=cell,
                available_context=plan.shared_context_schema,
                workflow_description=workflow_description,
                available_tools=self.available_tools
            )
            cell_code = code
            cell.mark_ready(code, cell.description)

            events.append({
                "type": "cell_ready",
                "cell_id": cell.id,
                "cell_name": cell.name,
                "display_step": cell.get_display_step(),
                "code_preview": code[:300] + "..." if len(code) > 300 else code,
                "full_code": code,
                "code_description": cell.description,
                "success_criteria": cell.success_criteria,
                "timestamp": datetime.utcnow().isoformat()
            })
        except Exception as e:
            logger.error("Failed to generate code for cell '{}': {}".format(cell.name, str(e)))
            cell.mark_failed(str(e))
            events.append({
                "type": "cell_failed",
                "cell_id": cell.id,
                "cell_name": cell.name,
                "display_step": cell.get_display_step(),
                "error": "Code generation failed: {}".format(str(e)),
                "timestamp": datetime.utcnow().isoformat()
            })
            return {"cell": cell, "success": False, "events": events, "example_outputs": {}}

        evaluation_attempt = 0
        evaluation_history = []  # Accumulate feedback across retries
        cell_passed_evaluation = False
        smoke_test_result = None

        while evaluation_attempt < self.max_evaluation_retries and not cell_passed_evaluation:
            evaluation_attempt += 1

            smoke_test_context = example_contexts[0].copy()

            events.append({
                "type": "cell_executing",
                "cell_id": cell.id,
                "cell_name": cell.name,
                "display_step": cell.get_display_step(),
                "step_number": cell.step_number,
                "is_smoke_test": True,
                "evaluation_attempt": evaluation_attempt,
                "timestamp": datetime.utcnow().isoformat()
            })

            try:
                start_time = time.time()
                smoke_test_result = await self._execute_cell_with_retry(
                    cell=cell,
                    code=cell_code,
                    context=smoke_test_context,
                    workflow_description=workflow_description
                )
                execution_time = time.time() - start_time

                output_variables = smoke_test_result.get("variables", {})
                formatted_outputs = self._format_output_variables(output_variables)

                smoke_test_output = ExampleOutput(
                    example_id="smoke_test",
                    user_input=smoke_test_context.get("user_input", ""),
                    output_text=smoke_test_result.get("output", ""),
                    output_variables=output_variables,
                    formatted_variables=formatted_outputs
                )

                events.append({
                    "type": "cell_smoke_test_completed",
                    "cell_id": cell.id,
                    "cell_name": cell.name,
                    "display_step": cell.get_display_step(),
                    "output": smoke_test_result.get("output", ""),
                    "variables": list(output_variables.keys()),
                    "variable_values": formatted_outputs,
                    "execution_time": execution_time,
                    "timestamp": datetime.utcnow().isoformat()
                })

            except Exception as e:
                logger.warning("Smoke test execution failed for cell '{}': {}".format(cell.name, str(e)))

                if evaluation_attempt >= self.max_evaluation_retries:
                    cell.mark_failed(str(e))
                    events.append({
                        "type": "cell_failed",
                        "cell_id": cell.id,
                        "cell_name": cell.name,
                        "display_step": cell.get_display_step(),
                        "error": str(e),
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    return {"cell": cell, "success": False, "events": events, "example_outputs": {}}

                events.append({
                    "type": "cell_retrying",
                    "cell_id": cell.id,
                    "cell_name": cell.name,
                    "display_step": cell.get_display_step(),
                    "attempt": evaluation_attempt + 1,
                    "max_attempts": self.max_evaluation_retries,
                    "previous_error": str(e),
                    "reason": "execution_error",
                    "timestamp": datetime.utcnow().isoformat()
                })

                cell_code = await self.fix_cell_code(
                    cell=cell,
                    failed_code=cell_code,
                    error_message=str(e),
                    execution_context=smoke_test_context,
                    workflow_description=workflow_description,
                    attempt_number=evaluation_attempt + 1,
                    output_example=plan.output_example if hasattr(plan, 'output_example') else None,
                    is_final_cell=(cell.step_number == len(plan.cells))
                )
                cell.mark_ready(cell_code, cell.code_description)

                events.append({
                    "type": "cell_code_fixed",
                    "cell_id": cell.id,
                    "cell_name": cell.name,
                    "display_step": cell.get_display_step(),
                    "full_code": cell_code,
                    "fix_reason": "execution_error",
                    "timestamp": datetime.utcnow().isoformat()
                })
                continue

            events.append({
                "type": "cell_evaluating",
                "cell_id": cell.id,
                "cell_name": cell.name,
                "display_step": cell.get_display_step(),
                "evaluation_attempt": evaluation_attempt,
                "timestamp": datetime.utcnow().isoformat()
            })

            # Only pass output_example to evaluator for the final cell
            is_final_cell = "final_result" in cell.outputs_produced
            cell_output_example = plan.output_example if is_final_cell else None

            evaluation_result = await self.cell_evaluator.evaluate_smoke_test_output(
                cell=cell,
                smoke_test_output=smoke_test_output,
                workflow_description=workflow_description,
                cell_code=cell_code,
                output_example=cell_output_example
            )

            if evaluation_result.is_valid:
                cell_passed_evaluation = True
                # Store evaluation metadata on cell
                cell.evaluation_score = getattr(evaluation_result, 'score', 1.0)
                cell.evaluation_attempts = evaluation_attempt
                cell.evaluation_history = evaluation_history if evaluation_history else None
                events.append({
                    "type": "cell_evaluation_passed",
                    "cell_id": cell.id,
                    "cell_name": cell.name,
                    "display_step": cell.get_display_step(),
                    "feedback": evaluation_result.feedback,
                    "score": getattr(evaluation_result, 'score', None),
                    "timestamp": datetime.utcnow().isoformat()
                })
            else:
                logger.warning("Evaluation failed for cell '{}': {}".format(cell.name, evaluation_result.feedback))

                # Accumulate evaluation feedback for history
                evaluation_history.append({
                    "attempt": evaluation_attempt,
                    "score": getattr(evaluation_result, 'score', None),
                    "feedback": evaluation_result.feedback,
                    "issues": evaluation_result.issues
                })

                events.append({
                    "type": "cell_evaluation_failed",
                    "cell_id": cell.id,
                    "cell_name": cell.name,
                    "display_step": cell.get_display_step(),
                    "feedback": evaluation_result.feedback,
                    "issues": evaluation_result.issues,
                    "evaluation_attempt": evaluation_attempt,
                    "max_attempts": self.max_evaluation_retries,
                    "timestamp": datetime.utcnow().isoformat()
                })

                if evaluation_attempt >= self.max_evaluation_retries:
                    eval_score = getattr(evaluation_result, 'score', 0.5)
                    if eval_score >= self.min_eval_score_to_proceed:
                        logger.warning("Max retries reached for cell '{}', proceeding with score {:.2f}".format(
                            cell.name, eval_score))
                        events.append({
                            "type": "cell_evaluation_max_retries",
                            "cell_id": cell.id,
                            "cell_name": cell.name,
                            "display_step": cell.get_display_step(),
                            "message": "Max retries reached, proceeding with acceptable score {:.2f}".format(eval_score),
                            "timestamp": datetime.utcnow().isoformat()
                        })
                        cell_passed_evaluation = True
                    else:
                        logger.error("Max retries reached for cell '{}' with low score {:.2f}, marking failed".format(
                            cell.name, eval_score))
                        cell.mark_failed("Evaluation failed after {} attempts (score: {:.2f})".format(
                            self.max_evaluation_retries, eval_score))
                        events.append({
                            "type": "cell_failed",
                            "cell_id": cell.id,
                            "cell_name": cell.name,
                            "display_step": cell.get_display_step(),
                            "error": "Evaluation failed with low score {:.2f} after {} attempts".format(
                                eval_score, self.max_evaluation_retries),
                            "timestamp": datetime.utcnow().isoformat()
                        })
                    # Store evaluation metadata regardless
                    cell.evaluation_score = eval_score
                    cell.evaluation_attempts = evaluation_attempt
                    cell.evaluation_history = evaluation_history
                else:
                    events.append({
                        "type": "cell_fixing_from_evaluation",
                        "cell_id": cell.id,
                        "cell_name": cell.name,
                        "display_step": cell.get_display_step(),
                        "feedback": evaluation_result.feedback,
                        "output_analysis": evaluation_result.output_analysis,
                        "timestamp": datetime.utcnow().isoformat()
                    })

                    single_example_result = [{
                        "user_input": smoke_test_context.get("user_input", ""),
                        "output": smoke_test_result.get("output", "") if smoke_test_result else "",
                        "variables": smoke_test_result.get("variables", {}) if smoke_test_result else {},
                        "formatted_variables": self._format_output_variables(
                            smoke_test_result.get("variables", {}) if smoke_test_result else {}
                        ),
                        "success": True
                    }]
                    cell_code = await self.fix_cell_code_from_evaluation(
                        cell=cell,
                        current_code=cell_code,
                        evaluation_result=evaluation_result,
                        all_example_results=single_example_result,
                        workflow_description=workflow_description,
                        attempt_number=evaluation_attempt + 1,
                        output_example=plan.output_example if hasattr(plan, 'output_example') and cell.step_number == len(plan.cells) else None,
                        evaluation_history=evaluation_history
                    )
                    cell.mark_ready(cell_code, cell.code_description)

                    events.append({
                        "type": "cell_code_fixed",
                        "cell_id": cell.id,
                        "cell_name": cell.name,
                        "display_step": cell.get_display_step(),
                        "full_code": cell_code,
                        "fix_reason": "evaluation_feedback",
                        "timestamp": datetime.utcnow().isoformat()
                    })

        # If cell was marked failed (e.g. low eval score), return early
        if cell.status == CellStatus.FAILED:
            return {"cell": cell, "success": False, "events": events, "example_outputs": {}}

        if smoke_test_result:
            example_contexts[0].update(smoke_test_result.get("variables", {}))
            example_outputs[0] = smoke_test_result.get("variables", {})

        first_example_output = {
            "output": smoke_test_result.get("output", "") if smoke_test_result else "",
            "variables": list(smoke_test_result.get("variables", {}).keys()) if smoke_test_result else [],
            "variable_values": self._format_output_variables(
                smoke_test_result.get("variables", {})
            ) if smoke_test_result else {}
        }

        events.append({
            "type": "cell_example_completed",
            "cell_id": cell.id,
            "cell_name": cell.name,
            "display_step": cell.get_display_step(),
            "example_index": 0,
            "example_id": examples[0].get("id", "example_0"),
            "output": first_example_output["output"],
            "variables": first_example_output["variables"],
            "variable_values": first_example_output["variable_values"],
            "timestamp": datetime.utcnow().isoformat()
        })

        for example_idx in range(1, total_examples):
            example = examples[example_idx]
            example_context = example_contexts[example_idx]

            events.append({
                "type": "cell_executing",
                "cell_id": cell.id,
                "cell_name": cell.name,
                "display_step": cell.get_display_step(),
                "step_number": cell.step_number,
                "is_smoke_test": False,
                "example_index": example_idx,
                "timestamp": datetime.utcnow().isoformat()
            })

            try:
                start_time = time.time()
                example_result = await self._execute_cell_with_retry(
                    cell=cell,
                    code=cell_code,
                    context=example_context,
                    workflow_description=workflow_description
                )
                execution_time = time.time() - start_time

                example_contexts[example_idx].update(example_result.get("variables", {}))
                example_outputs[example_idx] = example_result.get("variables", {})

                output_variables = example_result.get("variables", {})
                formatted_outputs = self._format_output_variables(output_variables)

                events.append({
                    "type": "cell_example_completed",
                    "cell_id": cell.id,
                    "cell_name": cell.name,
                    "display_step": cell.get_display_step(),
                    "example_index": example_idx,
                    "example_id": example.get("id", "example_{}".format(example_idx)),
                    "output": example_result.get("output", ""),
                    "variables": list(output_variables.keys()),
                    "variable_values": formatted_outputs,
                    "execution_time": execution_time,
                    "timestamp": datetime.utcnow().isoformat()
                })

            except Exception as e:
                logger.warning("Example {} execution failed for cell '{}': {}".format(
                    example_idx, cell.name, str(e)
                ))

                events.append({
                    "type": "cell_example_failed",
                    "cell_id": cell.id,
                    "cell_name": cell.name,
                    "display_step": cell.get_display_step(),
                    "example_index": example_idx,
                    "example_id": example.get("id", "example_{}".format(example_idx)),
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat()
                })

        cell.mark_completed(
            output="Completed for {} examples".format(total_examples),
            variables={},
            execution_time=0
        )

        events.append({
            "type": "cell_completed",
            "cell_id": cell.id,
            "cell_name": cell.name,
            "display_step": cell.get_display_step(),
            "step_number": cell.step_number,
            "layer": cell.layer,
            "total_examples": total_examples,
            "timestamp": datetime.utcnow().isoformat()
        })

        return {
            "cell": cell,
            "success": True,
            "events": events,
            "example_outputs": example_outputs
        }

    async def _execute_cell_with_all_examples_streaming(
        self,
        cell: WorkflowCell,
        examples: List[Dict[str, Any]],
        example_contexts: List[Dict[str, Any]],
        workflow_description: str,
        plan: WorkflowPlan,
        event_queue: asyncio.Queue
    ) -> Dict[str, Any]:
        """Execute a cell with all examples, evaluate outputs, and retry if evaluation fails."""
        cell_code = None
        total_examples = len(examples)

        async def emit(event: Dict[str, Any]):
            await event_queue.put(event)

        cell.mark_generating()
        await emit({
            "type": "cell_generating",
            "cell_id": cell.id,
            "cell_name": cell.name,
            "step_number": cell.step_number,
            "layer": cell.layer,
            "display_step": cell.get_display_step(),
            "description": cell.description,
            "timestamp": datetime.utcnow().isoformat()
        })

        try:
            code = await self.cell_generator.generate_cell_code(
                cell=cell,
                available_context=plan.shared_context_schema,
                workflow_description=workflow_description,
                available_tools=self.available_tools
            )
            cell_code = code
            cell.mark_ready(code, cell.description)

            await emit({
                "type": "cell_ready",
                "cell_id": cell.id,
                "cell_name": cell.name,
                "display_step": cell.get_display_step(),
                "code_preview": code[:300] + "..." if len(code) > 300 else code,
                "full_code": code,
                "code_description": cell.description,
                "success_criteria": cell.success_criteria,
                "timestamp": datetime.utcnow().isoformat()
            })
        except Exception as e:
            logger.error("Failed to generate code for cell '{}': {}".format(cell.name, str(e)))
            cell.mark_failed(str(e))
            await emit({
                "type": "cell_failed",
                "cell_id": cell.id,
                "cell_name": cell.name,
                "display_step": cell.get_display_step(),
                "error": "Code generation failed: {}".format(str(e)),
                "timestamp": datetime.utcnow().isoformat()
            })
            return {"cell": cell, "success": False, "example_outputs": {}}

        evaluation_attempt = 0
        evaluation_history = []  # Accumulate feedback across retries
        cell_passed_evaluation = False

        while evaluation_attempt < self.max_evaluation_retries and not cell_passed_evaluation:
            evaluation_attempt += 1

            example_outputs: Dict[int, Dict[str, Any]] = {}
            example_results: List[Dict[str, Any]] = []
            all_examples_succeeded = True
            execution_error = None

            await emit({
                "type": "cell_executing_all_examples",
                "cell_id": cell.id,
                "cell_name": cell.name,
                "display_step": cell.get_display_step(),
                "step_number": cell.step_number,
                "total_examples": total_examples,
                "evaluation_attempt": evaluation_attempt,
                "timestamp": datetime.utcnow().isoformat()
            })

            for example_idx in range(total_examples):
                example = examples[example_idx]
                example_context = example_contexts[example_idx].copy()

                await emit({
                    "type": "cell_executing",
                    "cell_id": cell.id,
                    "cell_name": cell.name,
                    "display_step": cell.get_display_step(),
                    "step_number": cell.step_number,
                    "example_index": example_idx,
                    "total_examples": total_examples,
                    "evaluation_attempt": evaluation_attempt,
                    "timestamp": datetime.utcnow().isoformat()
                })

                try:
                    start_time = time.time()
                    example_result = await self._execute_cell_with_retry(
                        cell=cell,
                        code=cell_code,
                        context=example_context,
                        workflow_description=workflow_description
                    )
                    execution_time = time.time() - start_time

                    output_variables = example_result.get("variables", {})
                    formatted_outputs = self._format_output_variables(output_variables)

                    example_outputs[example_idx] = output_variables
                    example_results.append({
                        "example_idx": example_idx,
                        "example_id": example.get("id", "example_{}".format(example_idx)),
                        "success": True,
                        "output": example_result.get("output", ""),
                        "variables": output_variables,
                        "formatted_variables": formatted_outputs,
                        "execution_time": execution_time
                    })

                    await emit({
                        "type": "cell_example_completed",
                        "cell_id": cell.id,
                        "cell_name": cell.name,
                        "display_step": cell.get_display_step(),
                        "example_index": example_idx,
                        "example_id": example.get("id", "example_{}".format(example_idx)),
                        "output": example_result.get("output", ""),
                        "variables": list(output_variables.keys()),
                        "variable_values": formatted_outputs,
                        "execution_time": execution_time,
                        "evaluation_attempt": evaluation_attempt,
                        "timestamp": datetime.utcnow().isoformat()
                    })

                except Exception as e:
                    logger.warning("Example {} execution failed for cell '{}': {}".format(
                        example_idx, cell.name, str(e)
                    ))
                    all_examples_succeeded = False
                    execution_error = str(e)

                    example_results.append({
                        "example_idx": example_idx,
                        "example_id": example.get("id", "example_{}".format(example_idx)),
                        "success": False,
                        "error": str(e)
                    })

                    await emit({
                        "type": "cell_example_failed",
                        "cell_id": cell.id,
                        "cell_name": cell.name,
                        "display_step": cell.get_display_step(),
                        "example_index": example_idx,
                        "example_id": example.get("id", "example_{}".format(example_idx)),
                        "error": str(e),
                        "evaluation_attempt": evaluation_attempt,
                        "timestamp": datetime.utcnow().isoformat()
                    })

            if not all_examples_succeeded:
                if evaluation_attempt >= self.max_evaluation_retries:
                    cell.mark_failed(execution_error or "Multiple examples failed")
                    await emit({
                        "type": "cell_failed",
                        "cell_id": cell.id,
                        "cell_name": cell.name,
                        "display_step": cell.get_display_step(),
                        "error": execution_error or "Multiple examples failed after max retries",
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    return {"cell": cell, "success": False, "example_outputs": example_outputs}

                await emit({
                    "type": "cell_retrying",
                    "cell_id": cell.id,
                    "cell_name": cell.name,
                    "display_step": cell.get_display_step(),
                    "attempt": evaluation_attempt + 1,
                    "max_attempts": self.max_evaluation_retries,
                    "previous_error": execution_error,
                    "reason": "execution_error",
                    "timestamp": datetime.utcnow().isoformat()
                })

                cell_code = await self.fix_cell_code(
                    cell=cell,
                    failed_code=cell_code,
                    error_message=execution_error,
                    execution_context=example_contexts[0],
                    workflow_description=workflow_description,
                    attempt_number=evaluation_attempt + 1,
                    output_example=plan.output_example if hasattr(plan, 'output_example') else None,
                    is_final_cell=(cell.step_number == len(plan.cells))
                )
                cell.mark_ready(cell_code, cell.code_description)

                await emit({
                    "type": "cell_code_fixed",
                    "cell_id": cell.id,
                    "cell_name": cell.name,
                    "display_step": cell.get_display_step(),
                    "full_code": cell_code,
                    "fix_reason": "execution_error",
                    "timestamp": datetime.utcnow().isoformat()
                })
                continue

            await emit({
                "type": "cell_evaluating",
                "cell_id": cell.id,
                "cell_name": cell.name,
                "display_step": cell.get_display_step(),
                "evaluation_attempt": evaluation_attempt,
                "total_examples_evaluated": total_examples,
                "timestamp": datetime.utcnow().isoformat()
            })

            all_example_outputs = []
            for idx, result in enumerate(example_results):
                if result.get("success", True):  # Include all results (default to success)
                    all_example_outputs.append(ExampleOutput(
                        example_id="example_{}".format(idx),
                        user_input=examples[idx].get("user_input", "") if idx < len(examples) else "",
                        output_text=result.get("output", ""),
                        output_variables=result.get("variables", {}),
                        formatted_variables=result.get("formatted_variables", {})
                    ))

            # Only pass output_example to evaluator for the final cell
            is_final_cell = "final_result" in cell.outputs_produced
            cell_output_example = plan.output_example if is_final_cell else None

            evaluation_result = await self.cell_evaluator.evaluate_all_examples_output(
                cell=cell,
                example_outputs=all_example_outputs,
                workflow_description=workflow_description,
                cell_code=cell_code,
                output_example=cell_output_example
            )

            if evaluation_result.is_valid:
                cell_passed_evaluation = True
                # Store evaluation metadata on cell
                cell.evaluation_score = getattr(evaluation_result, 'score', 1.0)
                cell.evaluation_attempts = evaluation_attempt
                cell.evaluation_history = evaluation_history if evaluation_history else None
                await emit({
                    "type": "cell_evaluation_passed",
                    "cell_id": cell.id,
                    "cell_name": cell.name,
                    "display_step": cell.get_display_step(),
                    "feedback": evaluation_result.feedback,
                    "score": getattr(evaluation_result, 'score', None),
                    "timestamp": datetime.utcnow().isoformat()
                })
            else:
                logger.warning("Evaluation failed for cell '{}': {}".format(cell.name, evaluation_result.feedback))

                # Accumulate evaluation feedback for history
                evaluation_history.append({
                    "attempt": evaluation_attempt,
                    "score": getattr(evaluation_result, 'score', None),
                    "feedback": evaluation_result.feedback,
                    "issues": evaluation_result.issues
                })

                await emit({
                    "type": "cell_evaluation_failed",
                    "cell_id": cell.id,
                    "cell_name": cell.name,
                    "display_step": cell.get_display_step(),
                    "feedback": evaluation_result.feedback,
                    "issues": evaluation_result.issues,
                    "evaluation_attempt": evaluation_attempt,
                    "max_attempts": self.max_evaluation_retries,
                    "timestamp": datetime.utcnow().isoformat()
                })

                if evaluation_attempt >= self.max_evaluation_retries:
                    eval_score = getattr(evaluation_result, 'score', 0.5)
                    if eval_score >= self.min_eval_score_to_proceed:
                        logger.warning("Max retries reached for cell '{}', proceeding with score {:.2f}".format(
                            cell.name, eval_score))
                        await emit({
                            "type": "cell_evaluation_max_retries",
                            "cell_id": cell.id,
                            "cell_name": cell.name,
                            "display_step": cell.get_display_step(),
                            "message": "Max retries reached, proceeding with acceptable score {:.2f}".format(eval_score),
                            "timestamp": datetime.utcnow().isoformat()
                        })
                        cell_passed_evaluation = True
                    else:
                        logger.error("Max retries reached for cell '{}' with low score {:.2f}, marking failed".format(
                            cell.name, eval_score))
                        cell.mark_failed("Evaluation failed after {} attempts (score: {:.2f})".format(
                            self.max_evaluation_retries, eval_score))
                        await emit({
                            "type": "cell_failed",
                            "cell_id": cell.id,
                            "cell_name": cell.name,
                            "display_step": cell.get_display_step(),
                            "error": "Evaluation failed with low score {:.2f} after {} attempts".format(
                                eval_score, self.max_evaluation_retries),
                            "timestamp": datetime.utcnow().isoformat()
                        })
                    # Store evaluation metadata regardless
                    cell.evaluation_score = eval_score
                    cell.evaluation_attempts = evaluation_attempt
                    cell.evaluation_history = evaluation_history
                else:
                    await emit({
                        "type": "cell_fixing_from_evaluation",
                        "cell_id": cell.id,
                        "cell_name": cell.name,
                        "display_step": cell.get_display_step(),
                        "feedback": evaluation_result.feedback,
                        "output_analysis": evaluation_result.output_analysis,
                        "timestamp": datetime.utcnow().isoformat()
                    })

                    cell_code = await self.fix_cell_code_from_evaluation(
                        cell=cell,
                        current_code=cell_code,
                        evaluation_result=evaluation_result,
                        all_example_results=example_results,
                        workflow_description=workflow_description,
                        attempt_number=evaluation_attempt + 1,
                        output_example=plan.output_example if hasattr(plan, 'output_example') and cell.step_number == len(plan.cells) else None,
                        evaluation_history=evaluation_history
                    )
                    cell.mark_ready(cell_code, cell.code_description)

                    await emit({
                        "type": "cell_code_fixed",
                        "cell_id": cell.id,
                        "cell_name": cell.name,
                        "display_step": cell.get_display_step(),
                        "full_code": cell_code,
                        "fix_reason": "evaluation_feedback",
                        "timestamp": datetime.utcnow().isoformat()
                    })

        # If cell was marked failed (e.g. low eval score), return early
        if cell.status == CellStatus.FAILED:
            return {"cell": cell, "success": False, "example_outputs": {}}

        for example_idx, outputs in example_outputs.items():
            if example_idx < len(example_contexts):
                example_contexts[example_idx].update(outputs)

        cell.mark_completed(
            output="Completed for {} examples".format(total_examples),
            variables={},
            execution_time=0
        )

        await emit({
            "type": "cell_completed",
            "cell_id": cell.id,
            "cell_name": cell.name,
            "display_step": cell.get_display_step(),
            "step_number": cell.step_number,
            "layer": cell.layer,
            "total_examples": total_examples,
            "timestamp": datetime.utcnow().isoformat()
        })

        return {
            "cell": cell,
            "success": True,
            "example_outputs": example_outputs
        }

    async def _execute_cell_with_retry(
        self,
        cell: WorkflowCell,
        code: str,
        context: Dict[str, Any],
        workflow_description: str,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """Execute cell code with automatic retry on runtime errors (not evaluation failures)."""
        current_code = code
        last_error = None

        for attempt in range(max_retries):
            try:
                result = await self._execute_cell_code(
                    current_code,
                    context,
                    cell.id
                )
                return result

            except asyncio.TimeoutError:
                raise asyncio.TimeoutError(
                    "Cell execution timed out after {}s".format(self.max_cell_execution_time)
                )
            except Exception as e:
                last_error = e
                logger.warning("Execution attempt {} failed for cell '{}': {}".format(
                    attempt + 1, cell.name, str(e)
                ))

                if attempt + 1 >= max_retries:
                    break

                import traceback
                error_msg = "Error: {}\n\nTraceback:\n{}".format(str(e), traceback.format_exc())

                current_code = await self.fix_cell_code(
                    cell=cell,
                    failed_code=current_code,
                    error_message=error_msg,
                    execution_context=context,
                    workflow_description=workflow_description,
                    attempt_number=attempt + 2,
                    output_example=None,
                    is_final_cell=False
                )

        raise Exception("Cell execution failed after {} attempts: {}".format(
            max_retries, str(last_error)
        ))


    async def execute_cell_with_full_validation(
        self,
        cell: WorkflowCell,
        execution_context: Dict[str, Any],
        workflow_description: str,
        output_example: Optional[str] = None,
        shared_context_schema: Optional[Dict[str, str]] = None,
        producer_return_hints: Optional[Dict[str, str]] = None
    ) -> CellExecutionResult:
        """Execute a single cell with code generation, execution retry, and LLM evaluation cycles."""
        events: List[Dict[str, Any]] = []
        cell_code = cell.generated_code
        attempt = 0
        evaluation_attempt = 0
        evaluation_history = []  # Accumulate feedback across retries
        last_error = None

        if cell.status == CellStatus.PENDING or cell_code is None:
            cell.mark_generating()
            events.append({
                "type": "cell_generating",
                "cell_id": cell.id,
                "cell_name": cell.name,
                "step_number": cell.step_number,
                "layer": cell.layer,
                "sublayer_index": cell.sublayer_index,
                "display_step": cell.get_display_step(),
                "description": cell.description,
                "timestamp": datetime.utcnow().isoformat()
            })

            try:
                code = await self.cell_generator.generate_cell_code(
                    cell=cell,
                    available_context=shared_context_schema or {},
                    workflow_description=workflow_description,
                    producer_return_hints=producer_return_hints,
                    available_tools=self.available_tools
                )
                cell_code = code
                cell.mark_ready(code, cell.description)
                events.append({
                    "type": "cell_ready",
                    "cell_id": cell.id,
                    "cell_name": cell.name,
                    "display_step": cell.get_display_step(),
                    "code_preview": code[:300] + "..." if len(code) > 300 else code,
                    "full_code": code,
                    "code_description": cell.description,
                    "success_criteria": cell.success_criteria,
                    "timestamp": datetime.utcnow().isoformat()
                })
            except Exception as e:
                error_msg = "Code generation failed: {}".format(str(e))
                cell.mark_failed(error_msg)
                events.append({
                    "type": "cell_failed",
                    "cell_id": cell.id,
                    "cell_name": cell.name,
                    "display_step": cell.get_display_step(),
                    "error": error_msg,
                    "timestamp": datetime.utcnow().isoformat()
                })
                return CellExecutionResult(
                    cell=cell,
                    success=False,
                    error=error_msg,
                    events=events
                )

        while attempt < self.max_retry_attempts:
            attempt += 1
            is_retry = attempt > 1

            try:
                if is_retry:
                    events.append({
                        "type": "cell_retrying",
                        "cell_id": cell.id,
                        "cell_name": cell.name,
                        "display_step": cell.get_display_step(),
                        "attempt": attempt,
                        "max_attempts": self.max_retry_attempts,
                        "previous_error": last_error,
                        "reason": "execution_error",
                        "timestamp": datetime.utcnow().isoformat()
                    })

                    cell_code = await self.fix_cell_code(
                        cell=cell,
                        failed_code=cell_code,
                        error_message=last_error,
                        execution_context=execution_context,
                        workflow_description=workflow_description,
                        attempt_number=attempt,
                        output_example=cell_output_example,
                        is_final_cell=is_final_cell
                    )
                    cell.mark_ready(cell_code, cell.code_description)

                cell.mark_executing()
                events.append({
                    "type": "cell_executing",
                    "cell_id": cell.id,
                    "cell_name": cell.name,
                    "display_step": cell.get_display_step(),
                    "step_number": cell.step_number,
                    "attempt": attempt,
                    "timestamp": datetime.utcnow().isoformat()
                })

                for required_input in cell.inputs_required:
                    if required_input not in execution_context:
                        logger.warning(
                            "MISSING INPUT: Cell '{}' requires '{}' but it's not in context. "
                            "Available keys: {}".format(
                                cell.name, required_input,
                                list(execution_context.keys())
                            )
                        )
                    elif execution_context[required_input] is None:
                        logger.warning(
                            "NULL INPUT: Cell '{}' input '{}' is None".format(
                                cell.name, required_input
                            )
                        )

                start_time = time.time()
                cell_result = await self._execute_cell_code(
                    cell_code,
                    execution_context,
                    cell.id
                )
                execution_time = time.time() - start_time

                output_variables = cell_result.get("variables", {})
                formatted_outputs = self._format_output_variables(output_variables)

                events.append({
                    "type": "cell_executed",
                    "cell_id": cell.id,
                    "cell_name": cell.name,
                    "display_step": cell.get_display_step(),
                    "output": cell_result.get("output", ""),
                    "execution_time": execution_time,
                    "timestamp": datetime.utcnow().isoformat()
                })

                cell_passed_evaluation = False
                evaluation_attempt = 0

                while evaluation_attempt < self.max_evaluation_retries and not cell_passed_evaluation:
                    evaluation_attempt += 1

                    smoke_test_output = ExampleOutput(
                        example_id="cell_{}".format(cell.id),
                        user_input=execution_context.get("user_input", ""),
                        output_text=cell_result.get("output", ""),
                        output_variables=output_variables,
                        formatted_variables=formatted_outputs
                    )

                    events.append({
                        "type": "cell_evaluating",
                        "cell_id": cell.id,
                        "cell_name": cell.name,
                        "display_step": cell.get_display_step(),
                        "evaluation_attempt": evaluation_attempt,
                        "timestamp": datetime.utcnow().isoformat()
                    })

                    # Only pass output_example to evaluator for the final cell
                    is_final_cell = "final_result" in cell.outputs_produced
                    cell_output_example = output_example if is_final_cell else None

                    evaluation_result = await self.cell_evaluator.evaluate_smoke_test_output(
                        cell=cell,
                        smoke_test_output=smoke_test_output,
                        workflow_description=workflow_description,
                        cell_code=cell_code,
                        output_example=cell_output_example
                    )

                    if evaluation_result.is_valid:
                        cell_passed_evaluation = True
                        # Store evaluation metadata on cell
                        cell.evaluation_score = getattr(evaluation_result, 'score', 1.0)
                        cell.evaluation_attempts = evaluation_attempt
                        cell.evaluation_history = evaluation_history if evaluation_history else None
                        events.append({
                            "type": "cell_evaluation_passed",
                            "cell_id": cell.id,
                            "cell_name": cell.name,
                            "display_step": cell.get_display_step(),
                            "feedback": evaluation_result.feedback,
                            "score": getattr(evaluation_result, 'score', None),
                            "timestamp": datetime.utcnow().isoformat()
                        })
                    else:
                        # Accumulate evaluation feedback for history
                        evaluation_history.append({
                            "attempt": evaluation_attempt,
                            "score": getattr(evaluation_result, 'score', None),
                            "feedback": evaluation_result.feedback,
                            "issues": evaluation_result.issues
                        })

                        events.append({
                            "type": "cell_evaluation_failed",
                            "cell_id": cell.id,
                            "cell_name": cell.name,
                            "display_step": cell.get_display_step(),
                            "feedback": evaluation_result.feedback,
                            "issues": evaluation_result.issues,
                            "evaluation_attempt": evaluation_attempt,
                            "max_attempts": self.max_evaluation_retries,
                            "timestamp": datetime.utcnow().isoformat()
                        })

                        if evaluation_attempt >= self.max_evaluation_retries:
                            eval_score = getattr(evaluation_result, 'score', 0.5)
                            if eval_score >= self.min_eval_score_to_proceed:
                                logger.warning("Max retries reached for cell '{}', proceeding with score {:.2f}".format(
                                    cell.name, eval_score))
                                events.append({
                                    "type": "cell_evaluation_max_retries",
                                    "cell_id": cell.id,
                                    "cell_name": cell.name,
                                    "display_step": cell.get_display_step(),
                                    "message": "Max retries reached, proceeding with acceptable score {:.2f}".format(eval_score),
                                    "timestamp": datetime.utcnow().isoformat()
                                })
                                cell_passed_evaluation = True
                            else:
                                logger.error("Max retries reached for cell '{}' with low score {:.2f}, marking failed".format(
                                    cell.name, eval_score))
                                cell.mark_failed("Evaluation failed after {} attempts (score: {:.2f})".format(
                                    self.max_evaluation_retries, eval_score))
                                events.append({
                                    "type": "cell_failed",
                                    "cell_id": cell.id,
                                    "cell_name": cell.name,
                                    "display_step": cell.get_display_step(),
                                    "error": "Evaluation failed with low score {:.2f} after {} attempts".format(
                                        eval_score, self.max_evaluation_retries),
                                    "timestamp": datetime.utcnow().isoformat()
                                })
                            # Store evaluation metadata regardless
                            cell.evaluation_score = eval_score
                            cell.evaluation_attempts = evaluation_attempt
                            cell.evaluation_history = evaluation_history
                        else:
                            events.append({
                                "type": "cell_fixing_from_evaluation",
                                "cell_id": cell.id,
                                "cell_name": cell.name,
                                "display_step": cell.get_display_step(),
                                "feedback": evaluation_result.feedback,
                                "output_analysis": evaluation_result.output_analysis,
                                "timestamp": datetime.utcnow().isoformat()
                            })

                            single_example_result = [{
                                "user_input": execution_context.get("user_input", ""),
                                "output": cell_result.get("output", ""),
                                "variables": output_variables,
                                "formatted_variables": formatted_outputs,
                                "success": True
                            }]
                            cell_code = await self.fix_cell_code_from_evaluation(
                                cell=cell,
                                current_code=cell_code,
                                evaluation_result=evaluation_result,
                                all_example_results=single_example_result,
                                workflow_description=workflow_description,
                                attempt_number=evaluation_attempt + 1,
                                output_example=cell_output_example,
                                evaluation_history=evaluation_history
                            )
                            cell.mark_ready(cell_code, cell.code_description)

                            cell.mark_executing()
                            start_time = time.time()
                            cell_result = await self._execute_cell_code(
                                cell_code,
                                execution_context,
                                cell.id
                            )
                            execution_time = time.time() - start_time
                            output_variables = cell_result.get("variables", {})
                            formatted_outputs = self._format_output_variables(output_variables)

                cell.mark_completed(
                    output=cell_result.get("output", ""),
                    variables=output_variables,
                    execution_time=execution_time
                )

                events.append({
                    "type": "cell_completed",
                    "cell_id": cell.id,
                    "cell_name": cell.name,
                    "display_step": cell.get_display_step(),
                    "step_number": cell.step_number,
                    "layer": cell.layer,
                    "output": cell_result.get("output", ""),
                    "variables": list(output_variables.keys()),
                    "variable_values": formatted_outputs,
                    "execution_time": execution_time,
                    "attempt": attempt,
                    "evaluation_attempts": evaluation_attempt,
                    "was_retried": attempt > 1,
                    "timestamp": datetime.utcnow().isoformat()
                })

                return CellExecutionResult(
                    cell=cell,
                    success=True,
                    output=cell_result.get("output", ""),
                    output_variables=output_variables,
                    events=events,
                    attempts=attempt
                )

            except asyncio.TimeoutError:
                error_msg = "Cell timed out after {}s".format(self.max_cell_execution_time)
                last_error = error_msg
                logger.warning("Cell '{}' timed out (attempt {}/{})".format(
                    cell.name, attempt, self.max_retry_attempts
                ))

            except Exception as e:
                import traceback
                error_msg = str(e)
                full_traceback = traceback.format_exc()
                last_error = "Error: {}\n\nTraceback:\n{}".format(error_msg, full_traceback)
                logger.warning("Cell '{}' failed (attempt {}/{}): {}".format(
                    cell.name, attempt, self.max_retry_attempts, error_msg
                ))

        cell.mark_failed(last_error or "Unknown error")
        events.append({
            "type": "cell_failed",
            "cell_id": cell.id,
            "cell_name": cell.name,
            "display_step": cell.get_display_step(),
            "step_number": cell.step_number,
            "error": last_error,
            "attempts_made": attempt,
            "timestamp": datetime.utcnow().isoformat()
        })

        return CellExecutionResult(
            cell=cell,
            success=False,
            error=last_error,
            events=events,
            attempts=attempt
        )

    async def execute_layer(
        self,
        layer_cells: List[WorkflowCell],
        execution_context: Dict[str, Any],
        workflow_description: str,
        output_example: Optional[str] = None,
        shared_context_schema: Optional[Dict[str, str]] = None,
        producer_return_hints: Optional[Dict[str, str]] = None
    ) -> Tuple[bool, Dict[str, Any], List[Dict[str, Any]]]:
        """Execute all cells in a layer in parallel, each with full retry/evaluation cycles."""
        if not layer_cells:
            return True, execution_context.copy(), []

        layer = layer_cells[0].layer
        logger.info("Executing layer {} with {} cells in parallel".format(
            layer, len(layer_cells)
        ))

        tasks = [
            self.execute_cell_with_full_validation(
                cell=cell,
                execution_context=execution_context.copy(),
                workflow_description=workflow_description,
                output_example=output_example,
                shared_context_schema=shared_context_schema,
                producer_return_hints=producer_return_hints
            )
            for cell in layer_cells
        ]

        results: List[CellExecutionResult] = await asyncio.gather(*tasks)

        all_events: List[Dict[str, Any]] = []
        for result in results:
            all_events.extend(result.events)

        all_succeeded = all(result.success for result in results)
        failed_cells = [r.cell.name for r in results if not r.success]

        if not all_succeeded:
            logger.warning("Layer {} failed: cells {} did not complete".format(
                layer, failed_cells
            ))

        merged_context = execution_context.copy()
        for result in results:
            if result.success and result.output_variables:
                merged_context.update(result.output_variables)

        from ..core.executor import workflow_executor
        if layer_cells:
            workflow_executor.store_execution_context(
                layer_cells[0].workflow_id,
                merged_context
            )

        logger.info("Layer {} complete: {} successes, {} failures".format(
            layer,
            sum(1 for r in results if r.success),
            sum(1 for r in results if not r.success)
        ))

        return all_succeeded, merged_context, all_events

    async def execute_workflow_parallel(
        self,
        plan: WorkflowPlan,
        user_input: str,
        attached_file_ids: Optional[List[int]] = None,
        workflow_description: str = ""
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute workflow layer by layer with parallel cells and merged context between layers."""
        execution_context: Dict[str, Any] = {
            "user_input": user_input,
            "attached_file_ids": attached_file_ids or []
        }

        producer_return_hints: Dict[str, str] = {}

        layers = plan.get_cells_by_layer()
        total_layers = len(layers)
        total_cells = len(plan.cells)

        logger.info("Starting parallel workflow execution: {} layers, {} cells".format(
            total_layers, total_cells
        ))

        yield {
            "type": "workflow_start",
            "total_cells": total_cells,
            "total_layers": total_layers,
            "is_parallel": plan.is_parallel_workflow(),
            "timestamp": datetime.utcnow().isoformat()
        }

        completed_cells = 0

        for layer_num in sorted(layers.keys()):
            layer_cells = layers[layer_num]
            is_parallel_layer = len(layer_cells) > 1

            yield {
                "type": "layer_started",
                "layer": layer_num,
                "cell_count": len(layer_cells),
                "cells": [{"id": c.id, "name": c.name, "display_step": c.get_display_step()} for c in layer_cells],
                "parallel": is_parallel_layer,
                "timestamp": datetime.utcnow().isoformat()
            }

            success, merged_context, events = await self.execute_layer(
                layer_cells=layer_cells,
                execution_context=execution_context,
                workflow_description=workflow_description,
                output_example=plan.output_example,
                shared_context_schema=plan.shared_context_schema,
                producer_return_hints=producer_return_hints
            )

            for event in events:
                yield event

            if not success:
                failed_cells = [c for c in layer_cells if c.status == CellStatus.FAILED]

                yield {
                    "type": "layer_failed",
                    "layer": layer_num,
                    "failed_cells": [{"id": c.id, "name": c.name, "error": c.error} for c in failed_cells],
                    "timestamp": datetime.utcnow().isoformat()
                }

                yield {
                    "type": "workflow_failed",
                    "error": "Layer {} failed: cells {} did not complete".format(
                        layer_num,
                        [c.name for c in failed_cells]
                    ),
                    "completed_cells": completed_cells,
                    "failed_layer": layer_num,
                    "timestamp": datetime.utcnow().isoformat()
                }
                return

            execution_context = merged_context
            completed_cells += len(layer_cells)

            for cell in layer_cells:
                if cell.generated_code and cell.outputs_produced:
                    new_hints = self._extract_return_hints(
                        cell.generated_code, cell.outputs_produced
                    )
                    producer_return_hints.update(new_hints)

            yield {
                "type": "layer_completed",
                "layer": layer_num,
                "cell_count": len(layer_cells),
                "all_passed": True,
                "timestamp": datetime.utcnow().isoformat()
            }

        final_result = execution_context.get("final_result", "Workflow completed successfully")

        yield {
            "type": "workflow_completed",
            "final_result": final_result,
            "total_cells": total_cells,
            "completed_cells": completed_cells,
            "total_layers": total_layers,
            "timestamp": datetime.utcnow().isoformat()
        }


cell_executor = CellExecutor()
