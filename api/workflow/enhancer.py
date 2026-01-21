"""
Workflow Description Enhancer

This module handles enhancing raw workflow descriptions into detailed,
actionable specifications using Claude AI. It separates the enhancement
logic from the core workflow generation for better maintainability.

Key Features:
    - Language preservation (French/English/etc.)
    - Parallelization optimization recommendations
    - Ambiguity detection and clarification requests
    - Paradigm API tool selection guidance
    - Detailed step-by-step workflow specifications

Architecture:
    - Loads enhancement prompt from markdown file
    - Uses Anthropic Claude for intelligent enhancement
    - Returns structured enhancement results
    - Maintains context for code generation
"""

import logging
from pathlib import Path
from typing import Dict, Any
from anthropic import Anthropic

logger = logging.getLogger(__name__)


def load_enhancement_prompt() -> str:
    """
    Load the workflow enhancement prompt template from markdown file.
    
    Returns:
        str: The enhancement prompt content, or empty string if not found
    """
    try:
        current_dir = Path(__file__).parent
        prompt_file = current_dir / "enhancer_prompt.md"
        
        if prompt_file.exists():
            with open(prompt_file, 'r', encoding='utf-8') as f:
                content = f.read()
            logger.info(f"✅ Loaded enhancement prompt from {prompt_file}")
            return content
        else:
            logger.warning(f"⚠️ Enhancement prompt not found at {prompt_file}")
            return ""
    except Exception as e:
        logger.error(f"❌ Error loading enhancement prompt: {e}")
        return ""


class WorkflowEnhancer:
    """
    Enhances raw workflow descriptions into detailed specifications.
    
    This class takes user-provided natural language workflow descriptions
    and transforms them into comprehensive, step-by-step specifications
    that can be effectively converted to executable code.
    
    Features:
        - Language preservation (responds in same language as input)
        - Automatic parallelization optimization
        - Ambiguity detection and clarification requests
        - Paradigm API tool selection guidance
        - Professional output formatting specifications
    """
    
    def __init__(self, anthropic_client: Anthropic):
        """
        Initialize the workflow enhancer.
        
        Args:
            anthropic_client: Configured Anthropic client for AI enhancement
        """
        self.anthropic_client = anthropic_client
        self._enhancement_prompt = None
    
    @property
    def enhancement_prompt(self) -> str:
        """
        Get the enhancement prompt, loading it lazily on first access.
        
        Returns:
            str: The enhancement prompt template
        """
        if self._enhancement_prompt is None:
            self._enhancement_prompt = load_enhancement_prompt()
            
            # Fallback prompt if file loading fails
            if not self._enhancement_prompt:
                logger.warning("⚠️ Using fallback enhancement prompt")
                self._enhancement_prompt = self._get_fallback_prompt()
        
        return self._enhancement_prompt
    
    def _get_fallback_prompt(self) -> str:
        """
        Get a minimal fallback prompt if the main prompt file cannot be loaded.
        
        Returns:
            str: Basic enhancement prompt
        """
        return """You are an AI assistant that helps create detailed workflow descriptions.

Your task is to enhance the user's workflow description into clear, specific steps.

CRITICAL RULES:
1. Respond in the EXACT SAME LANGUAGE as the user's input
2. Break down workflows into specific steps
3. Identify operations that can run in parallel for better performance
4. Preserve ALL details from the original description

For each step, use this format:

STEP X: [Detailed description of what needs to be done]

QUESTIONS AND LIMITATIONS: [List any unclear points or missing information]

Enhance this workflow description:"""

    async def enhance_workflow_description(self, raw_description: str) -> Dict[str, Any]:
        """
        Enhance a raw workflow description using Claude AI to create a more detailed,
        actionable workflow specification with proper tool usage and clear steps.
        
        Args:
            raw_description: User's initial natural language workflow description
            
        Returns:
            Dict containing enhanced description, questions, and warnings
            
        Raises:
            Exception: If enhancement fails due to API or processing errors
        """
        try:
            user_message = f"Raw workflow description: {raw_description}"
            
            logger.info(f"🔄 Enhancing workflow description: {raw_description[:100]}...")
            
            response = self.anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=12000,  # Increased for complex workflows
                system=self.enhancement_prompt,
                messages=[{"role": "user", "content": user_message}]
            )
            
            result_text = response.content[0].text.strip()
            
            if not result_text:
                logger.warning("⚠️ Empty enhancement result, using original description")
                result_text = raw_description
            
            logger.info(f"✅ Enhanced workflow description ({len(result_text)} chars)")
            
            # Parse plain text response
            # Note: Questions and warnings are now embedded in the enhanced steps
            return {
                "enhanced_description": result_text,
                "questions": [],  # Questions are embedded in QUESTIONS AND LIMITATIONS sections
                "warnings": []    # Warnings are embedded in QUESTIONS AND LIMITATIONS sections
            }
                
        except Exception as e:
            error_msg = f"Workflow description enhancement failed: {str(e)}"
            logger.error(f"❌ {error_msg}")
            raise Exception(error_msg)
    