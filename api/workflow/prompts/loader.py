# Centralized prompt loader with file caching for workflow modules.

import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class PromptLoader:
    """Loads and caches prompt markdown files from the prompts directory."""

    _cache: Dict[str, str] = {}
    _prompts_dir: Optional[Path] = None

    @classmethod
    def _get_prompts_dir(cls) -> Path:
        """Return the prompts directory path."""
        if cls._prompts_dir is None:
            cls._prompts_dir = Path(__file__).parent
        return cls._prompts_dir

    @classmethod
    def load(cls, prompt_name: str) -> str:
        """Load a prompt by name (without .md extension), with caching."""
        if prompt_name in cls._cache:
            logger.debug("Using cached prompt: {}".format(prompt_name))
            return cls._cache[prompt_name]

        prompts_dir = cls._get_prompts_dir()
        prompt_file = prompts_dir / "{}.md".format(prompt_name)

        if not prompt_file.exists():
            error_msg = "Prompt file not found: {}".format(prompt_file)
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)

        try:
            with open(prompt_file, 'r', encoding='utf-8') as f:
                content = f.read()

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
        """Load a prompt, returning default if not found."""
        try:
            return cls.load(prompt_name)
        except (FileNotFoundError, IOError) as e:
            logger.warning("Could not load prompt '{}', using default: {}".format(
                prompt_name, str(e)
            ))
            return default

    @classmethod
    def clear_cache(cls) -> None:
        """Clear all cached prompts."""
        cls._cache.clear()
        logger.info("Prompt cache cleared")

    @classmethod
    def is_cached(cls, prompt_name: str) -> bool:
        """Check if a prompt is currently cached."""
        return prompt_name in cls._cache
