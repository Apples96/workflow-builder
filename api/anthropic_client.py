"""
Anthropic Claude API Client

This module provides direct HTTP-based API clients for Anthropic's Claude AI service.

Features:
    - Direct HTTP requests using aiohttp for async operations
    - Code generation from workflow descriptions
    - General-purpose chat completion
    - JSON response cleaning utilities

Usage:
    from .anthropic_client import anthropic_generate_code, anthropic_chat_completion

    code = await anthropic_generate_code("Create a workflow that...")
    response = await anthropic_chat_completion("What is the capital of France?")
"""
import aiohttp
import logging
from typing import Optional, Dict, Any

from .config import settings

# Set up logging
logger = logging.getLogger(__name__)


# ============================================================================
# JSON CLEANING UTILITIES
# ============================================================================

def clean_json_response(text: str) -> str:
    """
    Clean JSON response by removing markdown code blocks and extra whitespace.

    Sometimes AI responses wrap JSON in markdown code blocks like:
    ```json
    {"key": "value"}
    ```

    This function removes those wrappers to get clean JSON that can be parsed.

    Args:
        text: Raw text response that may contain JSON wrapped in markdown

    Returns:
        str: Cleaned JSON string ready for parsing

    Examples:
        >>> clean_json_response('```json\\n{"name": "test"}\\n```')
        '{"name": "test"}'

        >>> clean_json_response('{"name": "test"}')
        '{"name": "test"}'
    """
    if not text:
        return text

    # Remove markdown code block markers
    text = text.strip()

    # Remove ```json at the start
    if text.startswith('```json'):
        text = text[7:]  # Remove '```json'
    elif text.startswith('```'):
        text = text[3:]  # Remove '```'

    # Remove ``` at the end
    if text.endswith('```'):
        text = text[:-3]

    # Strip whitespace
    text = text.strip()

    return text


# ============================================================================
# ANTHROPIC CLAUDE API CLIENT (Direct HTTP)
# ============================================================================

async def anthropic_generate_code(
    workflow_description: str,
    context: Optional[Dict[str, Any]] = None,
    system_prompt: Optional[str] = None
) -> str:
    """
    Generate Python code from a workflow description using Claude via direct HTTP.

    Creates complete, self-contained workflow code that includes all necessary
    imports, API clients, and the main execution function. The generated code
    integrates with both Anthropic and Paradigm APIs.

    Args:
        workflow_description: Natural language description of the desired workflow
        context: Optional context dictionary with additional parameters
        system_prompt: Optional custom system prompt (uses default if None)

    Returns:
        str: Complete Python code ready for execution

    Raises:
        Exception: If API call fails or code generation fails

    Note:
        Generated code includes placeholder API keys that are replaced during execution
    """
    if not system_prompt:
        system_prompt = """You are a Python code generator for workflow automation.

        Your task is to generate executable Python code that implements the described workflow.

        Available tools:


        Requirements:
        1. Generate clean, executable Python code
        2. Use the available tools for LLM operations
        3. Handle errors gracefully
        4. Return results in the specified format
        5. Split complex tasks into clear steps

        The code should define a function called 'execute_workflow(user_input: str) -> str' that takes user input and returns the final result.

        Example workflow: "For each sentence in user input, search using paradigm_search, then format as 'Question: [sentence] Answer: [result]'"

        Example code structure:
        ```python
        def execute_workflow(user_input: str) -> str:
            # Implementation here
            return final_result
        ```"""

    user_prompt = f"""Generate Python code for this workflow:

{workflow_description}

Additional context: {context or 'None'}

Return only the Python code, no explanations or markdown formatting."""

    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 15000,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}]
    }

    headers = {
        "Content-Type": "application/json",
        "x-api-key": settings.anthropic_api_key,
        "anthropic-version": "2023-06-01"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                json=payload,
                headers=headers
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return result["content"][0]["text"]
                else:
                    error_text = await response.text()
                    raise Exception(f"Anthropic API error {response.status}: {error_text}")
    except Exception as e:
        raise Exception(f"Failed to generate code: {str(e)}")


async def anthropic_chat_completion(
    prompt: str,
    system_prompt: Optional[str] = None
) -> str:
    """
    Get a chat completion response from Claude via direct HTTP.

    General-purpose chat interface for AI responses. Used for tasks that
    don't require code generation, such as text analysis or Q&A.

    Args:
        prompt: User prompt or question
        system_prompt: Optional system instructions (default: helpful assistant)

    Returns:
        str: AI-generated response text

    Raises:
        Exception: If API call fails or response processing fails
    """
    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 1000,
        "system": system_prompt or "You are a helpful assistant.",
        "messages": [{"role": "user", "content": prompt}]
    }

    headers = {
        "Content-Type": "application/json",
        "x-api-key": settings.anthropic_api_key,
        "anthropic-version": "2023-06-01"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                json=payload,
                headers=headers
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return result["content"][0]["text"]
                else:
                    error_text = await response.text()
                    raise Exception(f"Anthropic API error {response.status}: {error_text}")
    except Exception as e:
        raise Exception(f"Chat completion failed: {str(e)}")


# ============================================================================
# COMPATIBILITY LAYER
# ============================================================================

class AnthropicClient:
    """
    Anthropic API client wrapper providing a clean interface for Claude operations.
    """
    def __init__(self):
        pass

    async def generate_code(
        self,
        workflow_description: str,
        context: Optional[Dict[str, Any]] = None,
        system_prompt: Optional[str] = None
    ) -> str:
        """Generate Python code from a workflow description."""
        return await anthropic_generate_code(workflow_description, context, system_prompt)

    async def chat_completion(
        self,
        prompt: str,
        system_prompt: Optional[str] = None
    ) -> str:
        """Get a chat completion response from Claude."""
        return await anthropic_chat_completion(prompt, system_prompt)


# Module exports
__all__ = [
    'clean_json_response',
    'anthropic_generate_code',
    'anthropic_chat_completion',
    'AnthropicClient',
]
