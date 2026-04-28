"""
Unit tests for Paradigm v3 response extraction.

Tests the _extract_v3_answer pure function that parses v3 Agent API responses.
"""

import pytest
from api.paradigm_client import _extract_v3_answer

pytestmark = pytest.mark.unit


class TestExtractV3Answer:
    """Tests for _extract_v3_answer response parsing."""

    def test_standard_response(self):
        """Extracts text from a normal v3 response."""
        response = {
            "messages": [
                {"role": "user", "parts": [{"type": "text", "text": "hi"}]},
                {"role": "assistant", "parts": [
                    {"type": "reasoning", "text": "thinking..."},
                    {"type": "text", "text": "Hello there!"},
                ]},
            ]
        }
        assert _extract_v3_answer(response) == "Hello there!"

    def test_empty_messages(self):
        """Returns empty string when messages list is empty."""
        assert _extract_v3_answer({"messages": []}) == ""

    def test_no_messages_key(self):
        """Returns empty string when response has no messages key."""
        assert _extract_v3_answer({}) == ""

    def test_no_text_parts(self):
        """Returns empty string when there are no text parts."""
        response = {
            "messages": [
                {"role": "assistant", "parts": [
                    {"type": "tool_call", "tool": "search"},
                ]},
            ]
        }
        assert _extract_v3_answer(response) == ""

    def test_multiple_text_parts_returns_last(self):
        """Returns the last text part when there are multiple."""
        response = {
            "messages": [
                {"role": "assistant", "parts": [
                    {"type": "text", "text": "first"},
                    {"type": "tool_call", "tool": "search"},
                    {"type": "text", "text": "final answer"},
                ]},
            ]
        }
        assert _extract_v3_answer(response) == "final answer"
