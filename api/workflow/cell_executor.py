"""
Cell-Based Workflow Executor

This module handles step-by-step execution of cell-based workflows.
It executes cells sequentially, passing state between them, and yields
events for real-time streaming to the frontend.

Key Components:
    - CellExecutor: Executes workflow cells one at a time
    - State management between cells
    - Real-time event streaming via async generators

The executor:
    - Generates code for each cell on-demand
    - Executes cells in dependency order
    - Passes outputs from one cell to the next via execution context
    - Yields SSE events for each stage of execution
    - Handles failures gracefully, preserving partial results
"""

import asyncio
import io
import json
import logging
import time
import re
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime
from typing import Optional, Dict, Any, List, AsyncGenerator

from .models import WorkflowCell, WorkflowPlan, CellStatus
from .cell_generator import CellCodeGenerator
from .cell_evaluator import CellOutputEvaluator, ExampleOutput, EvaluationResult
from ..config import settings

logger = logging.getLogger(__name__)


class CellExecutor:
    """
    Executes workflow cells one at a time with state passing.

    This executor handles the step-by-step execution of cell-based
    workflows, yielding events for real-time progress streaming.

    Attributes:
        max_cell_execution_time: Maximum seconds per cell (default 300)
        cell_generator: Generator for cell code
    """

    def __init__(self):
        """Initialize the cell executor."""
        self.max_cell_execution_time = 300  # 5 minutes per cell
        self.max_retry_attempts = 5  # Maximum retries for failed cells (execution errors)
        self.max_evaluation_retries = 5  # Maximum retries for evaluation failures
        self.cell_generator = CellCodeGenerator()
        self.cell_evaluator = CellOutputEvaluator()

    def _format_output_variables(self, variables: Dict[str, Any]) -> Dict[str, str]:
        """
        Format output variables for display in the UI.

        Args:
            variables: Dictionary of output variables

        Returns:
            Dictionary with formatted string representations
        """
        import json

        formatted = {}
        for key, value in variables.items():
            # Skip internal/technical variables
            if key in ["LIGHTON_API_KEY", "PARADIGM_API_KEY", "user_input", "attached_file_ids"]:
                continue

            # Format based on type
            if isinstance(value, dict):
                # Format dict as pretty JSON (limit to 500 chars)
                formatted_json = json.dumps(value, indent=2, ensure_ascii=False)
                if len(formatted_json) > 500:
                    formatted[key] = formatted_json[:500] + "\n... (truncated)"
                else:
                    formatted[key] = formatted_json
            elif isinstance(value, list):
                # Format lists nicely
                if len(value) == 0:
                    formatted[key] = "[]"
                elif len(value) <= 5:
                    # Show all items if 5 or fewer
                    formatted[key] = json.dumps(value, indent=2, ensure_ascii=False)
                else:
                    # Show first 5 items
                    formatted[key] = json.dumps(value[:5], indent=2, ensure_ascii=False) + "\n... ({} more items)".format(len(value) - 5)
            elif isinstance(value, str):
                # Truncate long strings
                if len(value) > 500:
                    formatted[key] = value[:500] + "... (truncated)"
                else:
                    formatted[key] = value
            else:
                # Numbers, booleans, etc.
                formatted[key] = str(value)

        return formatted

    def _load_cell_generation_guidance(self) -> str:
        """
        Load critical sections from the cell generation prompt.

        Returns:
            str: Key guidance sections for code generation
        """
        try:
            from pathlib import Path
            prompt_file = Path(__file__).parent / "cell_prompt.md"

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

    async def fix_cell_code(
        self,
        cell: WorkflowCell,
        failed_code: str,
        error_message: str,
        execution_context: Dict[str, Any],
        workflow_description: str,
        attempt_number: int
    ) -> str:
        """
        Use Claude to fix failed cell code.

        Args:
            cell: The cell that failed
            failed_code: The code that caused the error
            error_message: The error message/traceback
            execution_context: Current workflow context
            workflow_description: Overall workflow description
            attempt_number: Which retry attempt this is

        Returns:
            str: Fixed Python code
        """
        logger.info("Attempting to fix cell '{}' (attempt {}/{})".format(
            cell.name, attempt_number, self.max_retry_attempts
        ))

        # Load cell generation guidance
        generation_guidance = self._load_cell_generation_guidance()

        if generation_guidance:
            logger.info("Loaded {} chars of generation guidance for fix".format(len(generation_guidance)))
        else:
            logger.warning("No generation guidance loaded - fix may not be optimal")

        # Build context information
        context_summary = []
        for key, value in execution_context.items():
            if key not in ["LIGHTON_API_KEY", "PARADIGM_API_KEY"]:
                value_str = str(value)[:100]  # Truncate long values
                context_summary.append("  - {}: {}".format(key, value_str))

        context_info = "\n".join(context_summary) if context_summary else "  (none yet)"

        # Create the fix prompt with all necessary guidance
        fix_prompt = """You are debugging Python code that failed during execution. Fix the code to make it work correctly.

CRITICAL CODING GUIDELINES (MUST FOLLOW):
{generation_guidance}

WORKFLOW CONTEXT:
{workflow_description}

CELL INFORMATION:
- Cell Name: {cell_name}
- Cell Description: {cell_description}
- Step Number: {step_number}
- Expected Inputs: {inputs}
- Expected Outputs: {outputs}

CURRENT EXECUTION CONTEXT (available variables):
{context_info}

FAILED CODE:
```python
{failed_code}
```

ERROR MESSAGE:
{error_message}

DEBUGGING INSTRUCTIONS:
1. First, check the CRITICAL CODING GUIDELINES above - especially model robustness rules
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
            generation_guidance=generation_guidance,
            workflow_description=workflow_description,
            cell_name=cell.name,
            cell_description=cell.description,
            step_number=cell.step_number,
            inputs=", ".join(cell.inputs_required) if cell.inputs_required else "none",
            outputs=", ".join(cell.outputs_produced) if cell.outputs_produced else "none",
            context_info=context_info,
            failed_code=failed_code,
            error_message=error_message
        )

        # Call Claude to fix the code
        from anthropic import Anthropic
        anthropic_client = Anthropic(api_key=settings.anthropic_api_key)

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
            model="claude-sonnet-4-20250514",
            max_tokens=8000,
            system=system_prompt,
            messages=[{"role": "user", "content": fix_prompt}]
        )

        fixed_code = response.content[0].text

        # Clean up the code
        fixed_code = self.cell_generator._clean_code(fixed_code)

        logger.info("Generated fixed code for cell '{}' ({} chars)".format(
            cell.name, len(fixed_code)
        ))

        return fixed_code

    async def fix_cell_code_from_evaluation(
        self,
        cell: WorkflowCell,
        current_code: str,
        evaluation_result: EvaluationResult,
        execution_context: Dict[str, Any],
        workflow_description: str,
        attempt_number: int
    ) -> str:
        """
        Use Claude to fix cell code based on evaluation feedback.

        This is called when the smoke test output evaluation fails.
        Claude receives the evaluation feedback and fixes the code accordingly.

        Args:
            cell: The cell that produced invalid output
            current_code: The current code that needs fixing
            evaluation_result: The evaluation result with feedback and issues
            execution_context: Current workflow context
            workflow_description: Overall workflow description
            attempt_number: Which evaluation retry attempt this is

        Returns:
            str: Fixed Python code
        """
        logger.info("Fixing cell '{}' based on evaluation feedback (attempt {}/{})".format(
            cell.name, attempt_number, self.max_evaluation_retries
        ))

        # Load cell generation guidance
        generation_guidance = self._load_cell_generation_guidance()

        # Build context information
        context_summary = []
        for key, value in execution_context.items():
            if key not in ["LIGHTON_API_KEY", "PARADIGM_API_KEY"]:
                value_str = str(value)[:100]
                context_summary.append("  - {}: {}".format(key, value_str))

        context_info = "\n".join(context_summary) if context_summary else "  (none yet)"

        # Format issues list
        issues_text = "\n".join("- {}".format(issue) for issue in evaluation_result.issues) if evaluation_result.issues else "No specific issues listed"

        # Create the fix prompt with evaluation feedback
        fix_prompt = """You are fixing Python code that executed successfully but produced INCORRECT or INVALID output.
The code runs without errors, but the output doesn't meet expectations based on evaluation.

CRITICAL CODING GUIDELINES (MUST FOLLOW):
{generation_guidance}

WORKFLOW CONTEXT:
{workflow_description}

CELL INFORMATION:
- Cell Name: {cell_name}
- Cell Description: {cell_description}
- Step Number: {step_number}
- Expected Inputs: {inputs}
- Expected Outputs: {outputs}

CURRENT EXECUTION CONTEXT (available variables):
{context_info}

CURRENT CODE (executes but produces wrong output):
```python
{current_code}
```

EVALUATION FEEDBACK:
{feedback}

SPECIFIC ISSUES FOUND:
{issues}

SUGGESTED FIX FROM EVALUATOR:
{suggested_fix}

FIX INSTRUCTIONS:
1. The code RUNS without errors, but produces incorrect/invalid OUTPUT
2. Carefully read the evaluation feedback to understand what's wrong
3. Focus on fixing the OUTPUT, not the execution
4. Common issues include:
   - Wrong data structure returned
   - Missing fields in output
   - Incorrect parsing of API responses
   - Data not being extracted correctly
5. Keep the same function signature: async def execute_cell(context: Dict[str, Any]) -> Dict[str, Any]
6. Use print("CELL_OUTPUT: ...") for progress updates

Generate ONLY the corrected Python code - no markdown, no explanations.
The code must be complete and executable.
""".format(
            generation_guidance=generation_guidance,
            workflow_description=workflow_description,
            cell_name=cell.name,
            cell_description=cell.description,
            step_number=cell.step_number,
            inputs=", ".join(cell.inputs_required) if cell.inputs_required else "none",
            outputs=", ".join(cell.outputs_produced) if cell.outputs_produced else "none",
            context_info=context_info,
            current_code=current_code,
            feedback=evaluation_result.feedback,
            issues=issues_text,
            suggested_fix=evaluation_result.suggested_fix or "No specific fix suggested"
        )

        # Call Claude to fix the code
        from anthropic import Anthropic
        anthropic_client = Anthropic(api_key=settings.anthropic_api_key)

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
            model="claude-sonnet-4-20250514",
            max_tokens=8000,
            system=system_prompt,
            messages=[{"role": "user", "content": fix_prompt}]
        )

        fixed_code = response.content[0].text

        # Clean up the code
        fixed_code = self.cell_generator._clean_code(fixed_code)

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
        """
        Execute workflow cell by cell, yielding events as they occur.

        This is an async generator that yields SSE-compatible events
        for real-time streaming to the frontend.

        Args:
            plan: The workflow plan with cell definitions
            user_input: User's input query
            attached_file_ids: Optional list of attached file IDs
            workflow_description: Original workflow description

        Yields:
            dict: Event objects with type and relevant data

        Event Types:
            - workflow_start: Beginning of workflow execution
            - cell_generating: Code generation started for a cell
            - cell_ready: Cell code generated successfully
            - cell_executing: Cell execution started
            - cell_output: Intermediate output from cell
            - cell_completed: Cell finished successfully
            - cell_failed: Cell execution failed
            - workflow_completed: All cells finished successfully
            - workflow_failed: Workflow stopped due to cell failure
        """
        # Initialize execution context with user inputs
        execution_context: Dict[str, Any] = {
            "user_input": user_input,
            "attached_file_ids": attached_file_ids or []
        }

        total_cells = len(plan.cells)
        completed_cells = 0

        logger.info("Starting stepwise execution with {} cells".format(total_cells))

        # Emit workflow start event
        yield {
            "type": "workflow_start",
            "total_cells": total_cells,
            "timestamp": datetime.utcnow().isoformat()
        }

        # Execute each cell in order
        for cell in plan.cells:
            # Retry loop for each cell
            attempt = 0
            cell_succeeded = False
            last_error = None

            while attempt < self.max_retry_attempts and not cell_succeeded:
                attempt += 1
                is_retry = attempt > 1

                try:
                    # === Phase 1: Generate code for this cell ===
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

                        # Generate the cell code (or fix it if this is a retry)
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

                            # Use Claude to fix the failed code
                            code = await self.fix_cell_code(
                                cell=cell,
                                failed_code=cell.generated_code,
                                error_message=last_error,
                                execution_context=execution_context,
                                workflow_description=workflow_description,
                                attempt_number=attempt
                            )
                        else:
                            # First attempt - generate normally
                            description, code = await self.cell_generator.generate_cell_code(
                                cell=cell,
                                available_context=plan.shared_context_schema,
                                workflow_description=workflow_description
                            )

                        cell.mark_ready(code, description if not is_retry else None)

                        yield {
                            "type": "cell_ready",
                            "cell_id": cell.id,
                            "cell_name": cell.name,
                            "code_preview": code[:300] + "..." if len(code) > 300 else code,
                            "full_code": code,
                            "code_description": cell.code_description or description if not is_retry else cell.code_description,
                            "attempt": attempt,
                            "is_retry": is_retry,
                            "timestamp": datetime.utcnow().isoformat()
                        }

                    # === Phase 2: Execute the cell ===
                    cell.mark_executing()

                    yield {
                        "type": "cell_executing",
                        "cell_id": cell.id,
                        "cell_name": cell.name,
                        "step_number": cell.step_number,
                        "attempt": attempt,
                        "timestamp": datetime.utcnow().isoformat()
                    }

                    # Execute the cell and capture output
                    start_time = time.time()
                    cell_result = await self._execute_cell_code(
                        cell.generated_code,
                        execution_context,
                        cell.id
                    )
                    execution_time = time.time() - start_time

                    # Update context with cell outputs
                    output_variables = cell_result.get("variables", {})
                    execution_context.update(output_variables)

                    # Store updated execution context for cell reruns
                    from .executor import workflow_executor
                    workflow_executor.store_execution_context(plan.workflow_id, execution_context)

                    # Format output variables for display
                    formatted_outputs = self._format_output_variables(output_variables)

                    # Mark cell as completed
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
                        "variable_values": formatted_outputs,  # Add formatted values
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
                        # Final failure after all retries
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
                    # Otherwise, continue to next retry attempt

                except Exception as e:
                    import traceback
                    error_msg = str(e)
                    full_traceback = traceback.format_exc()
                    last_error = "Error: {}\n\nTraceback:\n{}".format(error_msg, full_traceback)

                    logger.warning("❌ Cell '{}' failed (attempt {}/{}): {}".format(
                        cell.name, attempt, self.max_retry_attempts, error_msg
                    ))

                    if attempt >= self.max_retry_attempts:
                        # Final failure after all retries
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
                    # Otherwise, continue to next retry attempt

        # All cells completed successfully
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
        """
        Execute a single cell's code with the given context.

        Args:
            code: The Python code to execute
            context: Input context dictionary
            cell_id: ID of the cell being executed

        Returns:
            dict: {
                "output": str,  # Human-readable output
                "variables": dict  # Variables produced by the cell
            }

        Raises:
            Exception: If execution fails
            asyncio.TimeoutError: If execution times out
        """
        # Inject API keys into the code
        code = self._inject_api_keys(code)

        # Create execution environment
        execution_globals = self._create_execution_environment()

        # Capture stdout for cell output messages
        output_lines: List[str] = []

        # Custom print function to capture CELL_OUTPUT messages
        original_print = print

        def capture_print(*args, sep=' ', end='\n', file=None, flush=False):
            message = sep.join(str(arg) for arg in args)

            # Capture CELL_OUTPUT messages
            if "CELL_OUTPUT:" in message:
                output_lines.append(message.replace("CELL_OUTPUT:", "").strip())

            # Also call original print for logging
            original_print(*args, sep=sep, end=end, file=file, flush=flush)

        execution_globals['print'] = capture_print

        try:
            # Compile the code
            compiled_code = compile(code, '<cell>', 'exec')

            # Execute with timeout
            result = await asyncio.wait_for(
                self._run_cell_code(compiled_code, execution_globals, context),
                timeout=self.max_cell_execution_time
            )

            # Format output
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
            # Restore original print
            execution_globals['print'] = original_print

    async def _run_cell_code(
        self,
        compiled_code,
        execution_globals: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Run the compiled cell code and return its output.

        Args:
            compiled_code: Compiled Python code
            execution_globals: Global namespace for execution
            context: Input context to pass to the cell

        Returns:
            dict: Output variables from the cell
        """
        stderr_capture = io.StringIO()

        try:
            with redirect_stderr(stderr_capture):
                # Execute the code to define the function
                exec(compiled_code, execution_globals)

                # Get the execute_cell function
                if 'execute_cell' not in execution_globals:
                    raise Exception("execute_cell function not found in generated code")

                cell_func = execution_globals['execute_cell']

                # Execute the cell function
                if asyncio.iscoroutinefunction(cell_func):
                    result = await cell_func(context)
                else:
                    result = cell_func(context)

                # Ensure result is a dictionary
                if not isinstance(result, dict):
                    result = {"final_result": str(result)}

                return result

        except Exception as e:
            stderr_content = stderr_capture.getvalue()
            if stderr_content:
                raise Exception("{}\nStderr: {}".format(str(e), stderr_content))
            raise

    def _inject_api_keys(self, code: str) -> str:
        """
        Inject actual API keys into the generated code.

        Args:
            code: The code with placeholder keys

        Returns:
            str: Code with actual keys injected
        """
        # Replace placeholder API keys with actual values
        code = code.replace(
            'LIGHTON_API_KEY = os.getenv("PARADIGM_API_KEY", "your_api_key_here")',
            'LIGHTON_API_KEY = "{}"'.format(settings.lighton_api_key)
        )
        code = code.replace(
            'LIGHTON_API_KEY = "your_api_key_here"',
            'LIGHTON_API_KEY = "{}"'.format(settings.lighton_api_key)
        )
        code = code.replace(
            'LIGHTON_BASE_URL = os.getenv("PARADIGM_BASE_URL", "https://paradigm.lighton.ai")',
            'LIGHTON_BASE_URL = "{}"'.format(settings.lighton_base_url)
        )

        return code

    def _create_execution_environment(self) -> Dict[str, Any]:
        """
        Create a safe execution environment for cell code.

        Returns:
            dict: Global namespace for code execution
        """
        return {
            '__name__': '__main__',
            '__builtins__': {
                # Basic types
                'len': len,
                'str': str,
                'int': int,
                'float': float,
                'bool': bool,
                'list': list,
                'dict': dict,
                'tuple': tuple,
                'set': set,

                # Iteration
                'range': range,
                'enumerate': enumerate,
                'zip': zip,
                'sorted': sorted,
                'reversed': reversed,

                # Math
                'sum': sum,
                'min': min,
                'max': max,
                'abs': abs,
                'round': round,

                # Type checking
                'isinstance': isinstance,
                'hasattr': hasattr,
                'getattr': getattr,
                'setattr': setattr,
                'type': type,

                # Exceptions
                'ValueError': ValueError,
                'TypeError': TypeError,
                'Exception': Exception,
                'RuntimeError': RuntimeError,
                'NameError': NameError,

                # Import support
                '__import__': __import__,

                # Other utilities
                'any': any,
                'all': all,
                'globals': globals,
                'print': print,

                # Class building
                '__build_class__': __build_class__,
                'object': object,
                'super': super,
                'property': property,
                'staticmethod': staticmethod,
                'classmethod': classmethod,

                # Binary types
                'bytes': bytes,
                'bytearray': bytearray,

                # Iteration internals
                'iter': iter,
                'next': next,
                'slice': slice,
                'map': map,
                'filter': filter,

                # Introspection
                'vars': vars,
                'dir': dir,
                'id': id,
                'hash': hash,

                # String/numeric conversion
                'ord': ord,
                'chr': chr,
                'bin': bin,
                'oct': oct,
                'hex': hex,

                # Math helpers
                'divmod': divmod,
                'pow': pow,
                'callable': callable,
            },
        }

    async def execute_workflow_with_evaluation(
        self,
        plan: WorkflowPlan,
        examples: List[Dict[str, Any]],
        workflow_description: str = ""
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Execute workflow with smoke test evaluation for multiple examples.

        Uses the "smoke test" approach:
        1. For each cell, execute with first example
        2. Evaluate the output using LLM as judge
        3. If evaluation fails, fix code and retry (up to 5 times)
        4. Once evaluation passes (or max retries), run remaining examples
        5. Move to next cell

        Args:
            plan: The workflow plan with cell definitions
            examples: List of example inputs, each with user_input and attached_file_ids
            workflow_description: Original workflow description

        Yields:
            dict: Event objects with type and relevant data

        Event Types (in addition to standard cell events):
            - cell_evaluating: Starting evaluation of smoke test output
            - cell_evaluation_passed: Evaluation passed
            - cell_evaluation_failed: Evaluation failed, will retry
            - cell_evaluation_max_retries: Max evaluation retries reached
        """
        if not examples:
            yield {
                "type": "error",
                "error": "No examples provided for execution",
                "timestamp": datetime.utcnow().isoformat()
            }
            return

        total_cells = len(plan.cells)
        total_examples = len(examples)

        logger.info("Starting execution with evaluation: {} cells, {} examples".format(
            total_cells, total_examples
        ))

        yield {
            "type": "workflow_start",
            "total_cells": total_cells,
            "total_examples": total_examples,
            "evaluation_enabled": True,
            "timestamp": datetime.utcnow().isoformat()
        }

        # Track execution contexts per example (each example has its own context flow)
        example_contexts: List[Dict[str, Any]] = []
        for i, example in enumerate(examples):
            example_contexts.append({
                "user_input": example.get("user_input", ""),
                "attached_file_ids": example.get("attached_file_ids", [])
            })

        completed_cells = 0

        # Execute each cell in order
        for cell in plan.cells:
            cell_code = None
            evaluation_attempt = 0
            cell_passed_evaluation = False

            # === Phase 1: Generate initial code ===
            cell.mark_generating()

            yield {
                "type": "cell_generating",
                "cell_id": cell.id,
                "cell_name": cell.name,
                "step_number": cell.step_number,
                "description": cell.description,
                "timestamp": datetime.utcnow().isoformat()
            }

            try:
                description, code = await self.cell_generator.generate_cell_code(
                    cell=cell,
                    available_context=plan.shared_context_schema,
                    workflow_description=workflow_description
                )
                cell_code = code
                cell.mark_ready(code, description)

                yield {
                    "type": "cell_ready",
                    "cell_id": cell.id,
                    "cell_name": cell.name,
                    "code_preview": code[:300] + "..." if len(code) > 300 else code,
                    "full_code": code,
                    "code_description": description,
                    "timestamp": datetime.utcnow().isoformat()
                }
            except Exception as e:
                logger.error("Failed to generate code for cell '{}': {}".format(cell.name, str(e)))
                cell.mark_failed(str(e))
                yield {
                    "type": "cell_failed",
                    "cell_id": cell.id,
                    "cell_name": cell.name,
                    "error": "Code generation failed: {}".format(str(e)),
                    "timestamp": datetime.utcnow().isoformat()
                }
                yield {
                    "type": "workflow_failed",
                    "error": "Cell '{}' code generation failed".format(cell.name),
                    "completed_cells": completed_cells,
                    "timestamp": datetime.utcnow().isoformat()
                }
                return

            # === Phase 2: Smoke test + evaluation loop ===
            while evaluation_attempt < self.max_evaluation_retries and not cell_passed_evaluation:
                evaluation_attempt += 1

                # Execute smoke test (first example)
                smoke_test_context = example_contexts[0].copy()

                yield {
                    "type": "cell_executing",
                    "cell_id": cell.id,
                    "cell_name": cell.name,
                    "step_number": cell.step_number,
                    "is_smoke_test": True,
                    "evaluation_attempt": evaluation_attempt,
                    "timestamp": datetime.utcnow().isoformat()
                }

                try:
                    start_time = time.time()
                    smoke_test_result = await self._execute_cell_with_retry(
                        cell=cell,
                        code=cell_code,
                        context=smoke_test_context,
                        workflow_description=workflow_description
                    )
                    execution_time = time.time() - start_time

                    # Prepare output for evaluation
                    output_variables = smoke_test_result.get("variables", {})
                    formatted_outputs = self._format_output_variables(output_variables)

                    smoke_test_output = ExampleOutput(
                        example_id="smoke_test",
                        user_input=smoke_test_context.get("user_input", ""),
                        output_text=smoke_test_result.get("output", ""),
                        output_variables=output_variables,
                        formatted_variables=formatted_outputs
                    )

                    # Emit smoke test completed
                    yield {
                        "type": "cell_smoke_test_completed",
                        "cell_id": cell.id,
                        "cell_name": cell.name,
                        "output": smoke_test_result.get("output", ""),
                        "variables": list(output_variables.keys()),
                        "variable_values": formatted_outputs,
                        "execution_time": execution_time,
                        "timestamp": datetime.utcnow().isoformat()
                    }

                except Exception as e:
                    # Smoke test execution failed (runtime error)
                    logger.warning("Smoke test execution failed for cell '{}': {}".format(
                        cell.name, str(e)
                    ))

                    if evaluation_attempt >= self.max_evaluation_retries:
                        cell.mark_failed(str(e))
                        yield {
                            "type": "cell_failed",
                            "cell_id": cell.id,
                            "cell_name": cell.name,
                            "error": str(e),
                            "timestamp": datetime.utcnow().isoformat()
                        }
                        yield {
                            "type": "workflow_failed",
                            "error": "Cell '{}' failed after {} attempts".format(
                                cell.name, evaluation_attempt
                            ),
                            "completed_cells": completed_cells,
                            "timestamp": datetime.utcnow().isoformat()
                        }
                        return

                    # Try to fix with existing fix_cell_code method
                    yield {
                        "type": "cell_retrying",
                        "cell_id": cell.id,
                        "cell_name": cell.name,
                        "attempt": evaluation_attempt + 1,
                        "max_attempts": self.max_evaluation_retries,
                        "previous_error": str(e),
                        "reason": "execution_error",
                        "timestamp": datetime.utcnow().isoformat()
                    }

                    cell_code = await self.fix_cell_code(
                        cell=cell,
                        failed_code=cell_code,
                        error_message=str(e),
                        execution_context=smoke_test_context,
                        workflow_description=workflow_description,
                        attempt_number=evaluation_attempt + 1
                    )
                    cell.mark_ready(cell_code, cell.code_description)

                    yield {
                        "type": "cell_code_fixed",
                        "cell_id": cell.id,
                        "cell_name": cell.name,
                        "full_code": cell_code,
                        "fix_reason": "execution_error",
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    continue

                # === Phase 3: Evaluate smoke test output ===
                yield {
                    "type": "cell_evaluating",
                    "cell_id": cell.id,
                    "cell_name": cell.name,
                    "evaluation_attempt": evaluation_attempt,
                    "timestamp": datetime.utcnow().isoformat()
                }

                evaluation_result = await self.cell_evaluator.evaluate_smoke_test_output(
                    cell=cell,
                    smoke_test_output=smoke_test_output,
                    workflow_description=workflow_description,
                    cell_code=cell_code
                )

                if evaluation_result.is_valid:
                    cell_passed_evaluation = True

                    yield {
                        "type": "cell_evaluation_passed",
                        "cell_id": cell.id,
                        "cell_name": cell.name,
                        "feedback": evaluation_result.feedback,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                else:
                    logger.warning("Evaluation failed for cell '{}': {}".format(
                        cell.name, evaluation_result.feedback
                    ))

                    yield {
                        "type": "cell_evaluation_failed",
                        "cell_id": cell.id,
                        "cell_name": cell.name,
                        "feedback": evaluation_result.feedback,
                        "issues": evaluation_result.issues,
                        "evaluation_attempt": evaluation_attempt,
                        "max_attempts": self.max_evaluation_retries,
                        "timestamp": datetime.utcnow().isoformat()
                    }

                    if evaluation_attempt >= self.max_evaluation_retries:
                        # Max retries reached, proceed anyway
                        logger.warning("Max evaluation retries reached for cell '{}', proceeding anyway".format(
                            cell.name
                        ))

                        yield {
                            "type": "cell_evaluation_max_retries",
                            "cell_id": cell.id,
                            "cell_name": cell.name,
                            "message": "Max evaluation retries reached, proceeding with current code",
                            "timestamp": datetime.utcnow().isoformat()
                        }
                        cell_passed_evaluation = True  # Force proceed
                    else:
                        # Fix code based on evaluation feedback
                        yield {
                            "type": "cell_fixing_from_evaluation",
                            "cell_id": cell.id,
                            "cell_name": cell.name,
                            "feedback": evaluation_result.feedback,
                            "suggested_fix": evaluation_result.suggested_fix,
                            "timestamp": datetime.utcnow().isoformat()
                        }

                        cell_code = await self.fix_cell_code_from_evaluation(
                            cell=cell,
                            current_code=cell_code,
                            evaluation_result=evaluation_result,
                            execution_context=smoke_test_context,
                            workflow_description=workflow_description,
                            attempt_number=evaluation_attempt + 1
                        )
                        cell.mark_ready(cell_code, cell.code_description)

                        yield {
                            "type": "cell_code_fixed",
                            "cell_id": cell.id,
                            "cell_name": cell.name,
                            "full_code": cell_code,
                            "fix_reason": "evaluation_feedback",
                            "timestamp": datetime.utcnow().isoformat()
                        }

            # === Phase 4: Execute remaining examples ===
            # First, update context for first example with smoke test results
            if smoke_test_result:
                example_contexts[0].update(smoke_test_result.get("variables", {}))

            # Store first example output
            first_example_output = {
                "output": smoke_test_result.get("output", "") if smoke_test_result else "",
                "variables": list(smoke_test_result.get("variables", {}).keys()) if smoke_test_result else [],
                "variable_values": self._format_output_variables(
                    smoke_test_result.get("variables", {})
                ) if smoke_test_result else {}
            }

            yield {
                "type": "cell_example_completed",
                "cell_id": cell.id,
                "cell_name": cell.name,
                "example_index": 0,
                "example_id": examples[0].get("id", "example_0"),
                "output": first_example_output["output"],
                "variables": first_example_output["variables"],
                "variable_values": first_example_output["variable_values"],
                "timestamp": datetime.utcnow().isoformat()
            }

            # Execute remaining examples (2, 3, ...)
            for example_idx in range(1, total_examples):
                example = examples[example_idx]
                example_context = example_contexts[example_idx]

                yield {
                    "type": "cell_executing",
                    "cell_id": cell.id,
                    "cell_name": cell.name,
                    "step_number": cell.step_number,
                    "is_smoke_test": False,
                    "example_index": example_idx,
                    "timestamp": datetime.utcnow().isoformat()
                }

                try:
                    start_time = time.time()
                    example_result = await self._execute_cell_with_retry(
                        cell=cell,
                        code=cell_code,
                        context=example_context,
                        workflow_description=workflow_description
                    )
                    execution_time = time.time() - start_time

                    # Update context for this example
                    example_contexts[example_idx].update(example_result.get("variables", {}))

                    output_variables = example_result.get("variables", {})
                    formatted_outputs = self._format_output_variables(output_variables)

                    yield {
                        "type": "cell_example_completed",
                        "cell_id": cell.id,
                        "cell_name": cell.name,
                        "example_index": example_idx,
                        "example_id": example.get("id", "example_{}".format(example_idx)),
                        "output": example_result.get("output", ""),
                        "variables": list(output_variables.keys()),
                        "variable_values": formatted_outputs,
                        "execution_time": execution_time,
                        "timestamp": datetime.utcnow().isoformat()
                    }

                except Exception as e:
                    # Example execution failed - log but continue
                    logger.warning("Example {} execution failed for cell '{}': {}".format(
                        example_idx, cell.name, str(e)
                    ))

                    yield {
                        "type": "cell_example_failed",
                        "cell_id": cell.id,
                        "cell_name": cell.name,
                        "example_index": example_idx,
                        "example_id": example.get("id", "example_{}".format(example_idx)),
                        "error": str(e),
                        "timestamp": datetime.utcnow().isoformat()
                    }

            # === Cell completed for all examples ===
            cell.mark_completed(
                output="Completed for {} examples".format(total_examples),
                variables={},
                execution_time=0
            )
            completed_cells += 1

            yield {
                "type": "cell_completed",
                "cell_id": cell.id,
                "cell_name": cell.name,
                "step_number": cell.step_number,
                "total_examples": total_examples,
                "timestamp": datetime.utcnow().isoformat()
            }

        # All cells completed
        yield {
            "type": "workflow_completed",
            "total_cells": total_cells,
            "completed_cells": completed_cells,
            "total_examples": total_examples,
            "timestamp": datetime.utcnow().isoformat()
        }

    async def _execute_cell_with_retry(
        self,
        cell: WorkflowCell,
        code: str,
        context: Dict[str, Any],
        workflow_description: str,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """
        Execute cell code with automatic retry on execution errors.

        This handles runtime errors during execution, not evaluation failures.

        Args:
            cell: The cell being executed
            code: The code to execute
            context: Execution context
            workflow_description: Workflow description for fix attempts
            max_retries: Maximum retry attempts for execution errors

        Returns:
            dict: Execution result with output and variables

        Raises:
            Exception: If execution fails after all retries
        """
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

                # Try to fix the code
                import traceback
                error_msg = "Error: {}\n\nTraceback:\n{}".format(str(e), traceback.format_exc())

                current_code = await self.fix_cell_code(
                    cell=cell,
                    failed_code=current_code,
                    error_message=error_msg,
                    execution_context=context,
                    workflow_description=workflow_description,
                    attempt_number=attempt + 2
                )

        raise Exception("Cell execution failed after {} attempts: {}".format(
            max_retries, str(last_error)
        ))


# Global executor instance
cell_executor = CellExecutor()
