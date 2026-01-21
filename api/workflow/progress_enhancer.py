"""
Workflow Progress Enhancer

This module takes generated workflow code and enhances it with progress tracking
capabilities. It analyzes the workflow structure and inserts appropriate progress
reporting calls to enable real-time feedback during execution.

Key Features:
    - Code analysis to identify workflow steps and operations
    - Dynamic step name generation based on business context
    - Progress reporting function injection
    - Maintains original workflow functionality
    - Error-safe enhancement with fallback to original code

Architecture:
    - Loads progress enhancement prompt from markdown file
    - Uses Anthropic Claude for intelligent code enhancement
    - Returns enhanced code with progress tracking capabilities
    - Preserves all original workflow logic and structure
"""

import logging
import re
from pathlib import Path
from typing import Dict, Any
from anthropic import Anthropic

logger = logging.getLogger(__name__)


def load_progress_enhancement_prompt() -> str:
    """
    Load the progress enhancement prompt template from markdown file.
    
    Returns:
        str: The progress enhancement prompt content, or empty string if not found
    """
    try:
        current_dir = Path(__file__).parent
        prompt_file = current_dir / "progress_enhancer_prompt.md"
        
        if prompt_file.exists():
            with open(prompt_file, 'r', encoding='utf-8') as f:
                content = f.read()
            logger.info(f"✅ Loaded progress enhancement prompt from {prompt_file}")
            return content
        else:
            logger.warning(f"⚠️ Progress enhancement prompt not found at {prompt_file}")
            return ""
    except Exception as e:
        logger.error(f"❌ Error loading progress enhancement prompt: {e}")
        return ""


class WorkflowProgressEnhancer:
    """
    Enhances generated workflow code with progress tracking capabilities.
    
    This class analyzes existing Python workflow code and adds progress reporting
    functionality to enable real-time UI feedback during workflow execution.
    
    Features:
        - Identifies key workflow operations (API calls, data processing)
        - Generates business-friendly step names from code context
        - Inserts progress reporting calls at appropriate points
        - Maintains error handling and original functionality
        - Safe enhancement with fallback to original code
    """
    
    def __init__(self, anthropic_client: Anthropic):
        """
        Initialize the progress enhancer.
        
        Args:
            anthropic_client: Configured Anthropic client for code analysis
        """
        self.anthropic_client = anthropic_client
        self._progress_prompt = None
    
    @property
    def progress_enhancement_prompt(self) -> str:
        """
        Get the progress enhancement prompt, loading it lazily on first access.
        
        Returns:
            str: The progress enhancement prompt template
        """
        if self._progress_prompt is None:
            self._progress_prompt = load_progress_enhancement_prompt()
            
            # Fallback prompt if file loading fails
            if not self._progress_prompt:
                logger.warning("⚠️ Using fallback progress enhancement prompt")
                self._progress_prompt = self._get_fallback_prompt()
        
        return self._progress_prompt
    
    def _get_fallback_prompt(self) -> str:
        """
        Get a minimal fallback prompt if the main prompt file cannot be loaded.
        
        Returns:
            str: Basic progress enhancement prompt
        """
        return """You are a Python code expert that adds progress tracking to workflow code.

Your task is to analyze the provided workflow code and add progress reporting calls.

RULES:
1. Keep ALL original functionality unchanged
2. Add report_progress() calls at key workflow steps  
3. Generate descriptive step names based on code context
4. Add progress reporting function to the code
5. Handle errors with progress reporting

Add this function at the top after imports:
```python
def report_progress(step_type: str, step_id: str, step_name: str, details: str = "", error: str = ""):
    import json
    import time
    progress_msg = {
        "type": step_type,
        "step_id": step_id,
        "step_name": step_name,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "details": details
    }
    if error:
        progress_msg["error"] = error
    
    print("PROGRESS_UPDATE: {}".format(json.dumps(progress_msg)))
```

Then add progress calls before/after major operations like document_search, analyze_documents_with_polling, etc.

Enhance this workflow code:"""

    async def enhance_workflow_with_progress(
        self, 
        base_workflow_code: str, 
        workflow_description: str
    ) -> Dict[str, Any]:
        """
        Enhance workflow code with progress tracking capabilities.
        
        Args:
            base_workflow_code: Generated Python workflow code to enhance
            workflow_description: Original user workflow description for context
            
        Returns:
            Dict containing enhanced code and metadata
            
        Raises:
            Exception: If enhancement fails, returns original code for safety
        """
        try:
            logger.info(f"🔄 Enhancing workflow code with progress tracking...")
            logger.info(f"📝 Original description: {workflow_description[:100]}...")
            logger.info(f"📄 Base code length: {len(base_workflow_code)} characters")
            
            # Prepare enhancement request
            user_message = f"""WORKFLOW DESCRIPTION (for context): {workflow_description}

BASE WORKFLOW CODE TO ENHANCE:
{base_workflow_code}"""
            
            # Call Claude to enhance the code
            response = self.anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=15000,
                system=self.progress_enhancement_prompt,
                messages=[{"role": "user", "content": user_message}]
            )
            
            enhanced_code = response.content[0].text.strip()
            
            # Clean up the enhanced code - remove markdown formatting if present
            enhanced_code = self._clean_enhanced_code(enhanced_code)
            
            if not enhanced_code or len(enhanced_code) < len(base_workflow_code) * 0.8:
                logger.warning("⚠️ Enhanced code seems incomplete, using original")
                enhanced_code = base_workflow_code
            
            # Validate the enhanced code
            validation_result = self._validate_enhanced_code(enhanced_code)
            
            if not validation_result["valid"]:
                logger.error(f"❌ Enhanced code validation failed: {validation_result['error']}")
                logger.warning("⚠️ Using original code as fallback")
                enhanced_code = base_workflow_code
            
            # Analyze what progress steps were added
            progress_steps = self._extract_progress_steps(enhanced_code)
            
            logger.info(f"✅ Progress enhancement complete")
            logger.info(f"📊 Enhanced code length: {len(enhanced_code)} characters")
            logger.info(f"🎯 Progress steps identified: {len(progress_steps)}")
            
            return {
                "enhanced_code": enhanced_code,
                "progress_steps": progress_steps,
                "enhancement_success": validation_result["valid"],
                "fallback_used": enhanced_code == base_workflow_code
            }
                
        except Exception as e:
            logger.error(f"❌ Progress enhancement failed: {str(e)}")
            logger.warning("⚠️ Using original workflow code as fallback")
            
            # Return original code as safe fallback
            return {
                "enhanced_code": base_workflow_code,
                "progress_steps": [],
                "enhancement_success": False,
                "fallback_used": True,
                "error": str(e)
            }
    
    def _clean_enhanced_code(self, code: str) -> str:
        """
        Clean up enhanced code by removing markdown formatting.
        
        Args:
            code: Raw enhanced code from Claude
            
        Returns:
            str: Cleaned Python code
        """
        # Remove markdown code blocks
        if "```python" in code:
            code = code.split("```python")[1].split("```")[0]
        elif "```" in code:
            # Try to extract code from generic code blocks
            parts = code.split("```")
            if len(parts) >= 2:
                code = parts[1]
        
        # Remove leading/trailing whitespace
        code = code.strip()
        
        return code
    
    def _validate_enhanced_code(self, code: str) -> Dict[str, Any]:
        """
        Validate that enhanced code is syntactically correct and maintains structure.
        
        Args:
            code: Enhanced workflow code to validate
            
        Returns:
            Dict with validation results
        """
        try:
            # Check for syntax errors
            compile(code, '<enhanced_workflow>', 'exec')

            # Check for required function
            if 'def execute_workflow(' not in code:
                return {"valid": False, "error": "Missing execute_workflow function"}

            # Check for async definition
            if 'async def execute_workflow(' not in code:
                return {"valid": False, "error": "execute_workflow must be async"}

            # Check for progress function
            if 'def report_progress(' not in code:
                return {"valid": False, "error": "Missing report_progress function"}

            # Check for essential imports
            required_imports = ['import asyncio', 'import aiohttp']
            for imp in required_imports:
                if imp not in code:
                    return {"valid": False, "error": f"Missing required import: {imp}"}

            return {"valid": True, "error": None}

        except SyntaxError as e:
            return {"valid": False, "error": f"Syntax error in enhanced code: {str(e)}"}
        except Exception as e:
            return {"valid": False, "error": f"Validation error: {str(e)}"}
    
    def _extract_progress_steps(self, code: str) -> list:
        """
        Extract progress step information from enhanced code.
        
        Args:
            code: Enhanced workflow code
            
        Returns:
            List of detected progress steps
        """
        steps = []
        
        # Look for report_progress calls to identify steps
        progress_pattern = r'report_progress\(\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\']\s*(?:,\s*["\']([^"\']*)["\'])?\s*\)'
        
        matches = re.findall(progress_pattern, code)
        
        for match in matches:
            step_type, step_id, step_name, details = match
            if step_type == "step_start":  # Only count start steps to avoid duplicates
                steps.append({
                    "step_id": step_id,
                    "step_name": step_name,
                    "details": details
                })
        
        return steps


# Global progress enhancer instance (initialized when needed)
_progress_enhancer = None

def get_progress_enhancer(anthropic_client: Anthropic) -> WorkflowProgressEnhancer:
    """
    Get or create global progress enhancer instance.
    
    Args:
        anthropic_client: Anthropic client for the enhancer
        
    Returns:
        WorkflowProgressEnhancer instance
    """
    global _progress_enhancer
    if _progress_enhancer is None:
        _progress_enhancer = WorkflowProgressEnhancer(anthropic_client)
    return _progress_enhancer