"""
Cell-Based Workflow Executor

This module handles step-by-step execution of cell-based workflows.
It supports both sequential and parallel execution based on layer structure.

Key Components:
    - CellExecutor: Executes workflow cells with parallel layer support
    - State management between cells and layers
    - Real-time event streaming via async generators
    - Per-cell retry and LLM evaluation cycles

The executor:
    - Generates code for each cell on-demand (parallel within layers)
    - Executes cells in layer order (parallel within each layer)
    - Passes outputs from one layer to the next via execution context
    - Yields SSE events for each stage of execution
    - Handles failures gracefully, preserving partial results
    - Each cell has its own retry + evaluation cycle running in parallel

Parallelization:
    - Cells in the same layer execute concurrently
    - Each cell runs its full retry + evaluation cycle independently
    - A layer completes only when ALL cells reach final state
    - Layer N+1 starts only after layer N completes
    - Context is merged from all parallel cells before next layer
"""

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

from .models import WorkflowCell, WorkflowPlan, CellStatus
from .cell_generator import CellCodeGenerator
from .cell_evaluator import CellOutputEvaluator, ExampleOutput, EvaluationResult
from ..config import settings


@dataclass
class CellExecutionResult:
    """
    Result of executing a single cell with full retry/evaluation cycle.

    Attributes:
        cell: The cell that was executed
        success: Whether the cell completed successfully
        output: Human-readable output text
        output_variables: Variables produced by the cell
        events: List of events that occurred during execution
        error: Error message if failed
        attempts: Number of attempts made
    """
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

        Shows the FULL output without any truncation so users can see
        complete results for every cell.

        Args:
            variables: Dictionary of output variables

        Returns:
            Dictionary with formatted string representations (never truncated)
        """
        import json

        formatted = {}
        for key, value in variables.items():
            # Skip internal/technical variables
            if key in ["LIGHTON_API_KEY", "PARADIGM_API_KEY", "user_input", "attached_file_ids"]:
                continue

            # Format based on type - NO TRUNCATION
            if isinstance(value, dict):
                # Format dict as pretty JSON (full content)
                formatted[key] = json.dumps(value, indent=2, ensure_ascii=False)
            elif isinstance(value, list):
                # Format lists nicely (show all items)
                formatted[key] = json.dumps(value, indent=2, ensure_ascii=False)
            elif isinstance(value, str):
                # Show full string
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

        Uses layer-based parallelization with the "smoke test" approach:
        1. Group cells by layer
        2. For each layer, execute all cells in parallel
        3. Each cell runs: smoke test -> evaluate -> retry if needed -> remaining examples
        4. Wait for ALL cells in a layer to complete ALL examples before next layer
        5. Context is merged from all cells before moving to next layer

        This ensures proper layer synchronization while maintaining parallel execution
        within layers and LLM evaluation for quality assurance.

        Args:
            plan: The workflow plan with cell definitions
            examples: List of example inputs, each with user_input and attached_file_ids
            workflow_description: Original workflow description

        Yields:
            dict: Event objects with type and relevant data

        Event Types (in addition to standard cell events):
            - layer_started: Beginning of layer execution
            - layer_completed: All cells in layer finished
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

        # Group cells by layer for proper synchronization
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

        # Track execution contexts per example (each example has its own context flow)
        # This is shared across all cells and updated as layers complete
        example_contexts: List[Dict[str, Any]] = []
        for i, example in enumerate(examples):
            example_contexts.append({
                "user_input": example.get("user_input", ""),
                "attached_file_ids": example.get("attached_file_ids", [])
            })

        completed_cells = 0

        # Execute layer by layer to ensure proper synchronization
        for layer_num in sorted(layers.keys()):
            layer_cells = layers[layer_num]
            is_parallel_layer = len(layer_cells) > 1

            # Emit layer started event
            yield {
                "type": "layer_started",
                "layer": layer_num,
                "cell_count": len(layer_cells),
                "cells": [{"id": c.id, "name": c.name, "display_step": c.get_display_step()} for c in layer_cells],
                "parallel": is_parallel_layer,
                "timestamp": datetime.utcnow().isoformat()
            }

            # Create a queue for real-time event streaming
            event_queue: asyncio.Queue = asyncio.Queue()

            # Start layer execution in a separate task
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

            # Stream events from the queue in real-time until layer completes
            while not layer_task.done():
                try:
                    # Wait for events with a short timeout to check if task is done
                    event = await asyncio.wait_for(event_queue.get(), timeout=0.1)
                    yield event
                except asyncio.TimeoutError:
                    continue

            # Get the layer results
            layer_results = await layer_task

            # Drain any remaining events from the queue
            while not event_queue.empty():
                event = event_queue.get_nowait()
                yield event

            # Update example contexts with outputs from cells
            for result in layer_results:
                if result.get("success"):
                    cell_outputs = result.get("example_outputs", {})
                    for ex_idx, outputs in cell_outputs.items():
                        if ex_idx < len(example_contexts):
                            example_contexts[ex_idx].update(outputs)

            # Check if all cells in layer succeeded
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

            # Emit layer completed event
            yield {
                "type": "layer_completed",
                "layer": layer_num,
                "cell_count": len(layer_cells),
                "all_passed": True,
                "timestamp": datetime.utcnow().isoformat()
            }

        # All layers completed successfully
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
        """
        Execute all cells in a layer in parallel, each with full evaluation and all examples.

        This method ensures that ALL cells in the layer complete ALL their examples
        (including retries and evaluation cycles) before returning. Events are streamed
        in real-time via the event_queue.

        Args:
            layer_cells: List of cells in this layer
            examples: List of example inputs
            example_contexts: Current execution contexts per example
            workflow_description: Workflow description for code generation/fixing
            plan: The workflow plan
            event_queue: Queue to push events for real-time streaming

        Returns:
            List of results, one per cell, with output data (events already streamed)
        """
        if not layer_cells:
            return []

        # Execute all cells in parallel - each runs its full evaluation + examples cycle
        tasks = [
            self._execute_cell_with_all_examples_streaming(
                cell=cell,
                examples=examples,
                example_contexts=[ctx.copy() for ctx in example_contexts],  # Each cell gets copies
                workflow_description=workflow_description,
                plan=plan,
                event_queue=event_queue
            )
            for cell in layer_cells
        ]

        # Wait for ALL cells to complete before returning
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
        """
        Execute a single cell with full evaluation cycle and all examples.

        This is the core execution logic for one cell:
        1. Generate code
        2. Run smoke test (first example)
        3. Evaluate output with LLM
        4. Fix and retry if evaluation fails (up to max_evaluation_retries)
        5. Run remaining examples
        6. Return results

        Args:
            cell: The cell to execute
            examples: List of all example inputs
            example_contexts: Execution contexts for each example
            workflow_description: Workflow description
            plan: The workflow plan

        Returns:
            Dict with success status, events, and example outputs
        """
        events: List[Dict[str, Any]] = []
        cell_code = None
        example_outputs: Dict[int, Dict[str, Any]] = {}  # example_idx -> outputs
        total_examples = len(examples)

        # === Phase 1: Generate initial code ===
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
            description, code = await self.cell_generator.generate_cell_code(
                cell=cell,
                available_context=plan.shared_context_schema,
                workflow_description=workflow_description
            )
            cell_code = code
            cell.mark_ready(code, description)

            events.append({
                "type": "cell_ready",
                "cell_id": cell.id,
                "cell_name": cell.name,
                "display_step": cell.get_display_step(),
                "code_preview": code[:300] + "..." if len(code) > 300 else code,
                "full_code": code,
                "code_description": description,
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

        # === Phase 2: Smoke test + evaluation loop ===
        evaluation_attempt = 0
        cell_passed_evaluation = False
        smoke_test_result = None

        while evaluation_attempt < self.max_evaluation_retries and not cell_passed_evaluation:
            evaluation_attempt += 1

            # Execute smoke test (first example)
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

                # Try to fix with existing fix_cell_code method
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
                    attempt_number=evaluation_attempt + 1
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

            # === Phase 3: Evaluate smoke test output ===
            events.append({
                "type": "cell_evaluating",
                "cell_id": cell.id,
                "cell_name": cell.name,
                "display_step": cell.get_display_step(),
                "evaluation_attempt": evaluation_attempt,
                "timestamp": datetime.utcnow().isoformat()
            })

            evaluation_result = await self.cell_evaluator.evaluate_smoke_test_output(
                cell=cell,
                smoke_test_output=smoke_test_output,
                workflow_description=workflow_description,
                cell_code=cell_code
            )

            if evaluation_result.is_valid:
                cell_passed_evaluation = True
                events.append({
                    "type": "cell_evaluation_passed",
                    "cell_id": cell.id,
                    "cell_name": cell.name,
                    "display_step": cell.get_display_step(),
                    "feedback": evaluation_result.feedback,
                    "timestamp": datetime.utcnow().isoformat()
                })
            else:
                logger.warning("Evaluation failed for cell '{}': {}".format(cell.name, evaluation_result.feedback))

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
                    logger.warning("Max evaluation retries reached for cell '{}', proceeding anyway".format(cell.name))
                    events.append({
                        "type": "cell_evaluation_max_retries",
                        "cell_id": cell.id,
                        "cell_name": cell.name,
                        "display_step": cell.get_display_step(),
                        "message": "Max evaluation retries reached, proceeding with current code",
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    cell_passed_evaluation = True  # Force proceed
                else:
                    # Fix code based on evaluation feedback
                    events.append({
                        "type": "cell_fixing_from_evaluation",
                        "cell_id": cell.id,
                        "cell_name": cell.name,
                        "display_step": cell.get_display_step(),
                        "feedback": evaluation_result.feedback,
                        "suggested_fix": evaluation_result.suggested_fix,
                        "timestamp": datetime.utcnow().isoformat()
                    })

                    cell_code = await self.fix_cell_code_from_evaluation(
                        cell=cell,
                        current_code=cell_code,
                        evaluation_result=evaluation_result,
                        execution_context=smoke_test_context,
                        workflow_description=workflow_description,
                        attempt_number=evaluation_attempt + 1
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

        # === Phase 4: Execute remaining examples ===
        # First, update context for first example with smoke test results
        if smoke_test_result:
            example_contexts[0].update(smoke_test_result.get("variables", {}))
            example_outputs[0] = smoke_test_result.get("variables", {})

        # Store first example output
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

        # Execute remaining examples (2, 3, ...)
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

                # Update context for this example
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
                # Example execution failed - log but continue
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

        # === Cell completed for all examples ===
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
        """
        Execute a single cell with all examples, then evaluate (Alternative A approach).

        This approach runs ALL examples before evaluation to ensure:
        - All examples run with the same code
        - All outputs are available for the next layer
        - Evaluation can see patterns across all examples

        Flow:
        1. Generate code
        2. Run ALL examples
        3. Evaluate outputs from all examples
        4. If evaluation fails → fix code → go back to step 2
        5. If evaluation passes → cell complete with all outputs

        Args:
            cell: The cell to execute
            examples: List of all example inputs
            example_contexts: Execution contexts for each example
            workflow_description: Workflow description
            plan: The workflow plan
            event_queue: Queue to push events for real-time streaming

        Returns:
            Dict with success status and example outputs (events already streamed)
        """
        cell_code = None
        total_examples = len(examples)

        async def emit(event: Dict[str, Any]):
            """Helper to push event to queue."""
            await event_queue.put(event)

        # === Phase 1: Generate initial code ===
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
            description, code = await self.cell_generator.generate_cell_code(
                cell=cell,
                available_context=plan.shared_context_schema,
                workflow_description=workflow_description
            )
            cell_code = code
            cell.mark_ready(code, description)

            await emit({
                "type": "cell_ready",
                "cell_id": cell.id,
                "cell_name": cell.name,
                "display_step": cell.get_display_step(),
                "code_preview": code[:300] + "..." if len(code) > 300 else code,
                "full_code": code,
                "code_description": description,
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

        # === Phase 2: Execute ALL examples + evaluation loop ===
        evaluation_attempt = 0
        cell_passed_evaluation = False

        while evaluation_attempt < self.max_evaluation_retries and not cell_passed_evaluation:
            evaluation_attempt += 1

            # Reset outputs for this attempt - all examples will run with current code
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

            # Run ALL examples with current code
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

                    # Store results
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

            # === Phase 3: Handle execution failures or evaluate outputs ===
            if not all_examples_succeeded:
                # Some examples failed - need to fix code
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

                # Fix code based on first error encountered
                cell_code = await self.fix_cell_code(
                    cell=cell,
                    failed_code=cell_code,
                    error_message=execution_error,
                    execution_context=example_contexts[0],
                    workflow_description=workflow_description,
                    attempt_number=evaluation_attempt + 1
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
                continue  # Retry all examples with fixed code

            # All examples succeeded - now evaluate
            await emit({
                "type": "cell_evaluating",
                "cell_id": cell.id,
                "cell_name": cell.name,
                "display_step": cell.get_display_step(),
                "evaluation_attempt": evaluation_attempt,
                "total_examples_evaluated": total_examples,
                "timestamp": datetime.utcnow().isoformat()
            })

            # Build combined output for evaluation (using first example as primary)
            first_result = example_results[0] if example_results else {}
            evaluation_output = ExampleOutput(
                example_id="all_examples",
                user_input=examples[0].get("user_input", "") if examples else "",
                output_text=first_result.get("output", ""),
                output_variables=first_result.get("variables", {}),
                formatted_variables=first_result.get("formatted_variables", {})
            )

            evaluation_result = await self.cell_evaluator.evaluate_smoke_test_output(
                cell=cell,
                smoke_test_output=evaluation_output,
                workflow_description=workflow_description,
                cell_code=cell_code
            )

            if evaluation_result.is_valid:
                cell_passed_evaluation = True
                await emit({
                    "type": "cell_evaluation_passed",
                    "cell_id": cell.id,
                    "cell_name": cell.name,
                    "display_step": cell.get_display_step(),
                    "feedback": evaluation_result.feedback,
                    "timestamp": datetime.utcnow().isoformat()
                })
            else:
                logger.warning("Evaluation failed for cell '{}': {}".format(cell.name, evaluation_result.feedback))

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
                    logger.warning("Max evaluation retries reached for cell '{}', proceeding anyway".format(cell.name))
                    await emit({
                        "type": "cell_evaluation_max_retries",
                        "cell_id": cell.id,
                        "cell_name": cell.name,
                        "display_step": cell.get_display_step(),
                        "message": "Max evaluation retries reached, proceeding with current code",
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    cell_passed_evaluation = True  # Force proceed
                else:
                    await emit({
                        "type": "cell_fixing_from_evaluation",
                        "cell_id": cell.id,
                        "cell_name": cell.name,
                        "display_step": cell.get_display_step(),
                        "feedback": evaluation_result.feedback,
                        "suggested_fix": evaluation_result.suggested_fix,
                        "timestamp": datetime.utcnow().isoformat()
                    })

                    cell_code = await self.fix_cell_code_from_evaluation(
                        cell=cell,
                        current_code=cell_code,
                        evaluation_result=evaluation_result,
                        execution_context=example_contexts[0],
                        workflow_description=workflow_description,
                        attempt_number=evaluation_attempt + 1
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
                    # Continue to retry all examples with fixed code

        # === Phase 4: Update contexts and complete ===
        # Update the original example_contexts with final outputs
        for example_idx, outputs in example_outputs.items():
            if example_idx < len(example_contexts):
                example_contexts[example_idx].update(outputs)

        # Cell completed for all examples
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

    async def _execute_workflow_with_evaluation_sequential(
        self,
        plan: WorkflowPlan,
        examples: List[Dict[str, Any]],
        workflow_description: str = ""
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        DEPRECATED: Sequential execution for backward compatibility.

        Execute workflow cell by cell without layer parallelization.
        This is the old implementation kept for reference.
        Use execute_workflow_with_evaluation instead.
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

        logger.info("Starting SEQUENTIAL execution with evaluation: {} cells, {} examples".format(
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

        # Execute each cell in order (OLD SEQUENTIAL METHOD)
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


    async def execute_cell_with_full_validation(
        self,
        cell: WorkflowCell,
        execution_context: Dict[str, Any],
        workflow_description: str
    ) -> CellExecutionResult:
        """
        Execute a single cell with complete retry and evaluation cycles.

        This runs INDEPENDENTLY for each cell in a parallel layer.
        Each cell goes through:
        1. Code generation (if needed)
        2. Code execution with retry on errors (up to max_retry_attempts)
        3. LLM evaluation of output with retry on invalid (up to max_evaluation_retries)

        Args:
            cell: The cell to execute
            execution_context: Input context (variables from previous layers)
            workflow_description: Overall workflow description

        Returns:
            CellExecutionResult with success status, outputs, and events
        """
        events: List[Dict[str, Any]] = []
        cell_code = cell.generated_code
        attempt = 0
        evaluation_attempt = 0
        last_error = None

        # Phase 1: Generate code if not already generated
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
                description, code = await self.cell_generator.generate_cell_code(
                    cell=cell,
                    available_context={},  # Context schema would be passed here
                    workflow_description=workflow_description
                )
                cell_code = code
                cell.mark_ready(code, description)
                events.append({
                    "type": "cell_ready",
                    "cell_id": cell.id,
                    "cell_name": cell.name,
                    "display_step": cell.get_display_step(),
                    "code_preview": code[:300] + "..." if len(code) > 300 else code,
                    "full_code": code,
                    "code_description": description,
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

        # Phase 2: Execute with retry loop
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

                    # Fix the code based on error
                    cell_code = await self.fix_cell_code(
                        cell=cell,
                        failed_code=cell_code,
                        error_message=last_error,
                        execution_context=execution_context,
                        workflow_description=workflow_description,
                        attempt_number=attempt
                    )
                    cell.mark_ready(cell_code, cell.code_description)

                # Execute the cell
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

                start_time = time.time()
                cell_result = await self._execute_cell_code(
                    cell_code,
                    execution_context,
                    cell.id
                )
                execution_time = time.time() - start_time

                output_variables = cell_result.get("variables", {})
                formatted_outputs = self._format_output_variables(output_variables)

                # Execution succeeded - now do LLM evaluation
                events.append({
                    "type": "cell_executed",
                    "cell_id": cell.id,
                    "cell_name": cell.name,
                    "display_step": cell.get_display_step(),
                    "output": cell_result.get("output", ""),
                    "execution_time": execution_time,
                    "timestamp": datetime.utcnow().isoformat()
                })

                # Phase 3: LLM Evaluation loop
                cell_passed_evaluation = False
                evaluation_attempt = 0

                while evaluation_attempt < self.max_evaluation_retries and not cell_passed_evaluation:
                    evaluation_attempt += 1

                    # Prepare output for evaluation
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

                    evaluation_result = await self.cell_evaluator.evaluate_smoke_test_output(
                        cell=cell,
                        smoke_test_output=smoke_test_output,
                        workflow_description=workflow_description,
                        cell_code=cell_code
                    )

                    if evaluation_result.is_valid:
                        cell_passed_evaluation = True
                        events.append({
                            "type": "cell_evaluation_passed",
                            "cell_id": cell.id,
                            "cell_name": cell.name,
                            "display_step": cell.get_display_step(),
                            "feedback": evaluation_result.feedback,
                            "timestamp": datetime.utcnow().isoformat()
                        })
                    else:
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
                            # Max retries reached, proceed anyway
                            logger.warning(
                                "Max evaluation retries reached for cell '{}', proceeding anyway".format(cell.name)
                            )
                            events.append({
                                "type": "cell_evaluation_max_retries",
                                "cell_id": cell.id,
                                "cell_name": cell.name,
                                "display_step": cell.get_display_step(),
                                "message": "Max evaluation retries reached, proceeding with current output",
                                "timestamp": datetime.utcnow().isoformat()
                            })
                            cell_passed_evaluation = True  # Force proceed
                        else:
                            # Fix code based on evaluation feedback
                            events.append({
                                "type": "cell_fixing_from_evaluation",
                                "cell_id": cell.id,
                                "cell_name": cell.name,
                                "display_step": cell.get_display_step(),
                                "feedback": evaluation_result.feedback,
                                "suggested_fix": evaluation_result.suggested_fix,
                                "timestamp": datetime.utcnow().isoformat()
                            })

                            cell_code = await self.fix_cell_code_from_evaluation(
                                cell=cell,
                                current_code=cell_code,
                                evaluation_result=evaluation_result,
                                execution_context=execution_context,
                                workflow_description=workflow_description,
                                attempt_number=evaluation_attempt + 1
                            )
                            cell.mark_ready(cell_code, cell.code_description)

                            # Re-execute with fixed code
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

                # Cell completed successfully
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

        # All retries exhausted
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
        workflow_description: str
    ) -> Tuple[bool, Dict[str, Any], List[Dict[str, Any]]]:
        """
        Execute all cells in a layer in parallel.

        Each cell runs its FULL validation cycle independently:
        - Code generation
        - Execution with retry on errors
        - LLM evaluation with retry on invalid output

        The layer completes only when ALL cells have reached a final state
        (either completed successfully or exhausted all retries).

        Args:
            layer_cells: List of cells in this layer
            execution_context: Input context (variables from previous layers)
            workflow_description: Overall workflow description

        Returns:
            Tuple of:
            - success: True if all cells completed successfully
            - merged_context: Combined context with outputs from all cells
            - events: All events from all cells
        """
        if not layer_cells:
            return True, execution_context.copy(), []

        layer = layer_cells[0].layer
        logger.info("Executing layer {} with {} cells in parallel".format(
            layer, len(layer_cells)
        ))

        # Execute all cells in parallel - each with its own retry/evaluation cycle
        tasks = [
            self.execute_cell_with_full_validation(
                cell=cell,
                execution_context=execution_context.copy(),  # Each cell gets a copy
                workflow_description=workflow_description
            )
            for cell in layer_cells
        ]

        # Wait for all cells to complete (success or failure)
        results: List[CellExecutionResult] = await asyncio.gather(*tasks)

        # Collect all events from all cells
        all_events: List[Dict[str, Any]] = []
        for result in results:
            all_events.extend(result.events)

        # Check if all cells succeeded
        all_succeeded = all(result.success for result in results)
        failed_cells = [r.cell.name for r in results if not r.success]

        if not all_succeeded:
            logger.warning("Layer {} failed: cells {} did not complete".format(
                layer, failed_cells
            ))

        # Merge contexts from all successful cells
        merged_context = execution_context.copy()
        for result in results:
            if result.success and result.output_variables:
                merged_context.update(result.output_variables)

        # Store updated context
        from .executor import workflow_executor
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
        """
        Execute workflow with layer-based parallelization.

        Executes cells layer by layer:
        - All cells in a layer run in parallel
        - Each cell has its own retry + evaluation cycle
        - Layer N+1 only starts after ALL cells in layer N complete
        - Context is merged from all parallel cells before next layer

        Args:
            plan: The workflow plan with cell definitions
            user_input: User's input query
            attached_file_ids: Optional list of attached file IDs
            workflow_description: Original workflow description

        Yields:
            dict: Event objects with type and relevant data

        Event Types:
            - workflow_start: Beginning of workflow execution
            - layer_started: Beginning of layer execution
            - cell_generating, cell_ready, cell_executing, etc.: Cell-level events
            - layer_completed: All cells in layer finished
            - layer_failed: One or more cells in layer failed
            - workflow_completed: All layers finished successfully
            - workflow_failed: Workflow stopped due to layer failure
        """
        # Initialize execution context
        execution_context: Dict[str, Any] = {
            "user_input": user_input,
            "attached_file_ids": attached_file_ids or []
        }

        # Group cells by layer
        layers = plan.get_cells_by_layer()
        total_layers = len(layers)
        total_cells = len(plan.cells)

        logger.info("Starting parallel workflow execution: {} layers, {} cells".format(
            total_layers, total_cells
        ))

        # Emit workflow start event
        yield {
            "type": "workflow_start",
            "total_cells": total_cells,
            "total_layers": total_layers,
            "is_parallel": plan.is_parallel_workflow(),
            "timestamp": datetime.utcnow().isoformat()
        }

        completed_cells = 0

        # Execute layer by layer
        for layer_num in sorted(layers.keys()):
            layer_cells = layers[layer_num]
            is_parallel_layer = len(layer_cells) > 1

            # Emit layer started event
            yield {
                "type": "layer_started",
                "layer": layer_num,
                "cell_count": len(layer_cells),
                "cells": [{"id": c.id, "name": c.name, "display_step": c.get_display_step()} for c in layer_cells],
                "parallel": is_parallel_layer,
                "timestamp": datetime.utcnow().isoformat()
            }

            # Execute all cells in this layer in parallel
            success, merged_context, events = await self.execute_layer(
                layer_cells=layer_cells,
                execution_context=execution_context,
                workflow_description=workflow_description
            )

            # Yield all events from this layer's execution
            for event in events:
                yield event

            if not success:
                # Get list of failed cells
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

            # Update context for next layer
            execution_context = merged_context
            completed_cells += len(layer_cells)

            # Emit layer completed event
            yield {
                "type": "layer_completed",
                "layer": layer_num,
                "cell_count": len(layer_cells),
                "all_passed": True,
                "timestamp": datetime.utcnow().isoformat()
            }

        # All layers completed successfully
        final_result = execution_context.get("final_result", "Workflow completed successfully")

        yield {
            "type": "workflow_completed",
            "final_result": final_result,
            "total_cells": total_cells,
            "completed_cells": completed_cells,
            "total_layers": total_layers,
            "timestamp": datetime.utcnow().isoformat()
        }


# Global executor instance
cell_executor = CellExecutor()
