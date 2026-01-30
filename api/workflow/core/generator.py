import asyncio
import logging
import re
import os
from pathlib import Path
from typing import Optional, Dict, Any
from ..models import Workflow
from .enhancer import WorkflowEnhancer
from .progress_enhancer import get_progress_enhancer
from anthropic import Anthropic
from ...config import settings

logger = logging.getLogger(__name__)


def load_generator_prompt() -> str:
    """
    Load the workflow generator system prompt from markdown file.
    
    Returns:
        str: The generator system prompt content, or empty string if not found
    """
    try:
        current_dir = Path(__file__).parent
        prompt_file = current_dir.parent / "prompts" / "generator.md"
        
        if prompt_file.exists():
            with open(prompt_file, 'r', encoding='utf-8') as f:
                content = f.read()
            logger.info(f"✅ Loaded generator system prompt from {prompt_file}")
            return content
        else:
            logger.warning(f"⚠️ Generator system prompt not found at {prompt_file}")
            return ""
    except Exception as e:
        logger.error(f"❌ Error loading generator system prompt: {e}")
        return ""



# ============================================================================
# POST-PROCESSING FUNCTIONS FOR CODE GENERATION
# ============================================================================

def count_api_calls(code: str) -> int:
    """
    Count the number of Paradigm API calls in generated code.
    Used to detect complex workflows that need staggering.
    """
    # Count async paradigm_client calls
    patterns = [
        r'await\s+paradigm_client\.\w+\(',
        r'paradigm_client\.\w+\([^)]+\)'
    ]

    total_calls = 0
    for pattern in patterns:
        matches = re.findall(pattern, code)
        total_calls += len(matches)

    return total_calls


def add_staggering_to_workflow(code: str, description: str) -> str:
    """
    Add staggering (delays) between API calls for complex workflows.
    Prevents API overload and timeouts on workflows with many parallel calls.
    """
    api_call_count = count_api_calls(code)

    if api_call_count < 40:
        # Not a complex workflow, no staggering needed
        return code

    logger.info(f"🔧 Post-processing: Detected complex workflow ({api_call_count} API calls)")
    logger.info(f"   Adding staggering to prevent API overload")

    # Strategy: Add small delays between asyncio.gather() calls
    # Pattern: Find asyncio.gather() with many tasks and add delays

    # For now, we'll add a general instruction as a comment
    # More sophisticated implementation would parse AST and insert delays

    staggering_note = '''
# ⚠️ Post-processing note: This workflow has many API calls ({})
# Consider adding delays between groups of calls to prevent timeouts:
# await asyncio.sleep(2)  # Small delay between API call groups
'''.format(api_call_count)

    # Insert note after imports
    if "import asyncio" in code:
        code = code.replace("import asyncio", f"import asyncio{staggering_note}")

    logger.info(f"✅ Post-processing: Added staggering guidance for {api_call_count} API calls")

    return code


class WorkflowGenerator:
    def __init__(self):
        self.anthropic_client = Anthropic(api_key=settings.anthropic_api_key)
        self.enhancer = WorkflowEnhancer(self.anthropic_client)
        self.progress_enhancer = get_progress_enhancer(self.anthropic_client)

    async def generate_workflow(
        self,
        description: str,
        name: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        enable_progress_tracking: bool = True
    ) -> Workflow:
        """
        Generate a workflow from a natural language description
        Args:
            description: Natural language description of the workflow
            name: Optional name for the workflow
            context: Additional context for code generation
            enable_progress_tracking: Whether to enhance workflow with progress tracking
        Returns:
            Workflow object with generated code (optionally enhanced with progress)
        """
        workflow = Workflow(
            name=name,
            description=description,
            context=context
        )
        
        try:
            workflow.update_status("generating")

            # Retry mechanism for code generation (up to 3 attempts)
            max_retries = 3
            last_error = None

            for attempt in range(max_retries):
                try:
                    # Generate the code using Anthropic API
                    generated_code = await self._generate_code(description, context)

                    # Validate the generated code
                    validation_result = await self._validate_code(generated_code)

                    if validation_result["valid"]:
                        # Success! Code is valid
                        final_code = generated_code
                        
                        # Optional progress enhancement
                        if enable_progress_tracking:
                            try:
                                logger.info("🔄 Enhancing workflow with progress tracking...")
                                enhancement_result = await self.progress_enhancer.enhance_workflow_with_progress(
                                    generated_code, description
                                )
                                
                                if enhancement_result["enhancement_success"]:
                                    final_code = enhancement_result["enhanced_code"]
                                    logger.info("✅ Progress enhancement successful")
                                    
                                    # Store progress step information in workflow context
                                    if workflow.context is None:
                                        workflow.context = {}
                                    workflow.context["progress_steps"] = enhancement_result["progress_steps"]
                                    workflow.context["progress_enabled"] = True
                                else:
                                    logger.warning("⚠️ Progress enhancement failed, using base workflow")
                                    if workflow.context is None:
                                        workflow.context = {}
                                    workflow.context["progress_enabled"] = False
                                    workflow.context["progress_error"] = enhancement_result.get("error", "Unknown error")
                                    
                            except Exception as e:
                                logger.error(f"❌ Progress enhancement error: {str(e)}")
                                logger.warning("⚠️ Using base workflow without progress tracking")
                                if workflow.context is None:
                                    workflow.context = {}
                                workflow.context["progress_enabled"] = False
                                workflow.context["progress_error"] = str(e)
                        else:
                            # Progress tracking disabled
                            if workflow.context is None:
                                workflow.context = {}
                            workflow.context["progress_enabled"] = False
                        
                        workflow.generated_code = final_code
                        workflow.update_status("ready")
                        return workflow
                    else:
                        # Validation failed, prepare for retry
                        last_error = validation_result['error']
                        if attempt < max_retries - 1:
                            # Add error context for next attempt
                            if context is None:
                                context = {}
                            context['previous_error'] = f"Previous attempt had syntax error: {last_error}"
                            continue
                        else:
                            # Last attempt failed
                            raise Exception(f"Generated code validation failed after {max_retries} attempts: {last_error}")

                except Exception as e:
                    if "validation failed" in str(e).lower():
                        # Re-raise validation errors
                        raise
                    # Other errors during generation
                    last_error = str(e)
                    if attempt < max_retries - 1:
                        continue
                    raise

            # Should not reach here, but just in case
            raise Exception(f"Failed to generate valid code after {max_retries} attempts: {last_error}")

        except Exception as e:
            workflow.update_status("failed", str(e))
            raise e

    async def _generate_code(self, description: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        Generate Python code from workflow description
        """
        # Load system prompt from markdown file
        base_prompt = load_generator_prompt()
        if not base_prompt:
            logger.error("❌ Could not load generator system prompt")
            raise Exception("Generator system prompt not found")
        
        # Use the base prompt as-is (skills documentation is now included in the prompt file)
        system_prompt = base_prompt
        
        # Create enhanced description for the user message
        enhanced_description = f"""
Workflow Description: {description}
Additional Context: {context or 'None'}

Generate a complete, self-contained workflow that:
1. Includes all necessary imports and API client classes
2. Implements the execute_workflow function with the exact logic described
3. Can be copy-pasted and run independently on any server
4. Handles the workflow requirements exactly as specified
5. MANDATORY: If the workflow uses documents, implement the if/else pattern for attached_file_ids as shown in the CORRECT PATTERN section above
"""

        try:
            response = self.anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=15000,  # Increased for full code generation
                system=system_prompt,
                messages=[{"role": "user", "content": enhanced_description}]
            )
            
            code = response.content[0].text
            
            # Log the raw generated code for debugging
            logger.info("🔧 RAW GENERATED CODE:")
            logger.info("=" * 50)
            logger.info(code)
            logger.info("=" * 50)
            
            # Clean up the code - remove markdown formatting if present
            code = self._clean_generated_code(code)

            # Log the cleaned code for debugging
            logger.info("🔧 CLEANED GENERATED CODE:")
            logger.info("=" * 50)
            logger.info(code)
            logger.info("=" * 50)

            # ============================================================================
            # POST-PROCESSING: Apply automatic fixes based on workflow type
            # ============================================================================

            logger.info("🔄 POST-PROCESSING: Analyzing generated code...")

            # Post-processing: Add staggering for complex workflows
            code = add_staggering_to_workflow(code, description)

            logger.info("✅ POST-PROCESSING: Complete")

            return code
            
        except Exception as e:
            raise Exception("Code generation failed: {}".format(str(e)))


    def _clean_generated_code(self, code: str) -> str:
        """
        Clean up generated code by removing markdown formatting and ensuring proper structure
        """
        # Remove markdown code blocks
        if "```python" in code:
            code = code.split("```python")[1].split("```")[0]
        elif "```" in code:
            code = code.split("```")[1].split("```")[0]
        
        # Remove leading/trailing whitespace
        code = code.strip()
        
        # Ensure execute_workflow is async
        if "def execute_workflow(" in code and "async def execute_workflow(" not in code:
            code = code.replace("def execute_workflow(", "async def execute_workflow(")
        
        return code

    async def _validate_code(self, code: str) -> Dict[str, Any]:
        """
        Validate that the generated code is syntactically correct and has required structure
        """
        try:
            # Check for syntax errors
            compile(code, '<string>', 'exec')

            # Check for required function
            if 'def execute_workflow(' not in code:
                return {"valid": False, "error": "Missing execute_workflow function"}

            # Check for async definition
            if 'async def execute_workflow(' not in code:
                return {"valid": False, "error": "execute_workflow must be async"}

            # Check for required imports
            required_imports = ['import asyncio', 'import aiohttp']
            for imp in required_imports:
                if imp not in code:
                    return {"valid": False, "error": f"Missing required import: {imp}"}

            return {"valid": True, "error": None}

        except SyntaxError as e:
            # Save failed code for debugging
            import tempfile
            import os
            from datetime import datetime
            try:
                # Save to temp directory or current directory with timestamp
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"workflow_failed_{timestamp}.py"
                # Use tempfile.gettempdir() which works on Windows and Unix
                temp_dir = tempfile.gettempdir()
                filepath = os.path.join(temp_dir, filename)

                with open(filepath, 'w') as f:
                    f.write(code)
                    error_msg = f"❌ Syntax error - Failed code saved to: {filepath}"
                    print(error_msg)  # Force print to stdout
                    logger.error(error_msg)
                    logger.error(f"   Error: {str(e)}")
                    logger.error(f"   Line {e.lineno}: {e.text if e.text else 'N/A'}")
                    print(f"   Line {e.lineno}: {e.text if e.text else 'N/A'}")
            except Exception as save_error:
                logger.error(f"Could not save failed code: {save_error}")
            return {"valid": False, "error": f"Syntax error: {str(e)}"}
        except Exception as e:
            return {"valid": False, "error": f"Validation error: {str(e)}"}


# Global generator instance
workflow_generator = WorkflowGenerator()
