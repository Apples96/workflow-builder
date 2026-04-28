"""
Unit tests for the prompt loader.

Tests the caching contract and error handling — not the prompt content itself.
"""

import pytest
from api.workflow.prompts.loader import PromptLoader

pytestmark = pytest.mark.unit


class TestPromptLoader:
    """Tests for PromptLoader caching and loading behavior."""

    def test_load_existing_prompt(self):
        """Loading a known prompt returns non-empty content."""
        content = PromptLoader.load("planner")
        assert len(content) > 100

    def test_caching_behavior(self):
        """Second load returns cached result (is_cached confirms)."""
        assert PromptLoader.is_cached("planner") is False
        PromptLoader.load("planner")
        assert PromptLoader.is_cached("planner") is True

    def test_load_nonexistent_raises(self):
        """Loading a nonexistent prompt raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            PromptLoader.load("this_prompt_does_not_exist")

    def test_load_optional_returns_default(self):
        """load_optional returns default for missing prompts."""
        result = PromptLoader.load_optional("nonexistent_xyz", default="fallback")
        assert result == "fallback"

    def test_clear_cache(self):
        """clear_cache removes all cached prompts."""
        PromptLoader.load("planner")
        assert PromptLoader.is_cached("planner") is True
        PromptLoader.clear_cache()
        assert PromptLoader.is_cached("planner") is False
