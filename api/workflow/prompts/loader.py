"""
Prompt Loader Utility

This module provides a centralized, cached prompt loading mechanism for all
workflow generation modules. It eliminates duplicate prompt loading code across
enhancer, planner, generator, and evaluator modules.

Features:
    - Singleton-style caching to avoid repeated file reads
    - Consistent error handling across all prompt loads
    - Clear error messages when prompts are not found
    - Thread-safe caching via class-level dictionary

Usage:
    from .loader import PromptLoader

    # Load a prompt (cached after first load)
    prompt = PromptLoader.load("enhancer")  # Loads prompts/enhancer.md
    prompt = PromptLoader.load("planner")   # Loads prompts/planner.md
"""

import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class PromptLoader:
    """
    Centralized prompt loader with caching.

    Loads prompt files from the prompts directory and caches them
    in memory for subsequent accesses. This eliminates redundant
    file I/O and provides consistent error handling.

    Class Attributes:
        _cache: Dictionary mapping prompt names to their content
        _prompts_dir: Path to the prompts directory (set on first use)
    """

    _cache: Dict[str, str] = {}
    _prompts_dir: Optional[Path] = None

    @classmethod
    def _get_prompts_dir(cls) -> Path:
        """
        Get the prompts directory path.

        Returns:
            Path: Path to the prompts directory
        """
        if cls._prompts_dir is None:
            cls._prompts_dir = Path(__file__).parent
        return cls._prompts_dir

    @classmethod
    def load(cls, prompt_name: str) -> str:
        """
        Load a prompt from file with caching.

        Args:
            prompt_name: Name of the prompt file (without .md extension).
                        Supported names: enhancer, planner, cell, evaluator

        Returns:
            str: The prompt content

        Raises:
            FileNotFoundError: If the prompt file does not exist
            IOError: If the prompt file cannot be read
        """
        # Return cached version if available
        if prompt_name in cls._cache:
            logger.debug("Using cached prompt: {}".format(prompt_name))
            return cls._cache[prompt_name]

        # Build the file path
        prompts_dir = cls._get_prompts_dir()
        prompt_file = prompts_dir / "{}.md".format(prompt_name)

        # Load the prompt
        if not prompt_file.exists():
            error_msg = "Prompt file not found: {}".format(prompt_file)
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)

        try:
            with open(prompt_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # Cache the content
            cls._cache[prompt_name] = content
            logger.info("Loaded and cached prompt: {} ({} chars)".format(
                prompt_name, len(content)
            ))

            return content

        except IOError as e:
            error_msg = "Failed to read prompt file {}: {}".format(prompt_file, e)
            logger.error(error_msg)
            raise IOError(error_msg)

    @classmethod
    def load_optional(cls, prompt_name: str, default: str = "") -> str:
        """
        Load a prompt, returning a default value if not found.

        This is useful when a fallback prompt is acceptable.

        Args:
            prompt_name: Name of the prompt file (without .md extension)
            default: Default value to return if prompt not found

        Returns:
            str: The prompt content or default value
        """
        try:
            return cls.load(prompt_name)
        except (FileNotFoundError, IOError) as e:
            logger.warning("Could not load prompt '{}', using default: {}".format(
                prompt_name, str(e)
            ))
            return default

    @classmethod
    def clear_cache(cls) -> None:
        """
        Clear the prompt cache.

        This is useful for testing or when prompt files may have changed.
        """
        cls._cache.clear()
        logger.info("Prompt cache cleared")

    @classmethod
    def is_cached(cls, prompt_name: str) -> bool:
        """
        Check if a prompt is currently cached.

        Args:
            prompt_name: Name of the prompt to check

        Returns:
            bool: True if the prompt is cached
        """
        return prompt_name in cls._cache
