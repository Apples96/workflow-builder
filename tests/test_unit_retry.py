"""
Unit tests for retry logic.

Tests the retry behavior contract: exponential backoff, retryable error detection,
and the call_with_retry wrapper.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.clients.retry import _calculate_delay, _is_retryable_status_error, call_with_retry

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# _calculate_delay
# ---------------------------------------------------------------------------

class TestCalculateDelay:
    """Tests for backoff delay calculation."""

    def test_exponential_growth(self):
        """Delay roughly doubles with each attempt (before jitter)."""
        d0 = _calculate_delay(0, base_delay=1.0, max_delay=60.0)
        d1 = _calculate_delay(1, base_delay=1.0, max_delay=60.0)
        d2 = _calculate_delay(2, base_delay=1.0, max_delay=60.0)
        # d0 ≈ 1.1–1.3, d1 ≈ 2.2–2.6, d2 ≈ 4.4–5.2
        assert d0 < d1 < d2

    def test_capped_at_max_delay(self):
        """Delay never exceeds max_delay."""
        d = _calculate_delay(20, base_delay=1.0, max_delay=10.0)
        assert d <= 10.0


# ---------------------------------------------------------------------------
# _is_retryable_status_error
# ---------------------------------------------------------------------------

class TestIsRetryableStatusError:
    """Tests for retryable error detection."""

    def test_retryable_codes(self):
        """Status codes 429, 500, 502, 503, 504 are retryable."""
        try:
            from anthropic import APIStatusError
        except ImportError:
            pytest.skip("anthropic not installed")

        for code in (429, 500, 502, 503, 504):
            err = MagicMock(spec=APIStatusError)
            err.status_code = code
            # Need isinstance check to pass
            with patch("api.clients.retry.HAS_ANTHROPIC", True), \
                 patch("api.clients.retry.isinstance", side_effect=lambda obj, cls: True):
                pass
            # Simpler approach: create a real-ish mock
            err.__class__ = APIStatusError
            assert _is_retryable_status_error(err) is True

    def test_non_retryable_codes(self):
        """Status codes 400, 401, 403, 404 are NOT retryable."""
        try:
            from anthropic import APIStatusError
        except ImportError:
            pytest.skip("anthropic not installed")

        for code in (400, 401, 403, 404):
            err = MagicMock(spec=APIStatusError)
            err.status_code = code
            err.__class__ = APIStatusError
            assert _is_retryable_status_error(err) is False

    def test_regular_exception_not_retryable(self):
        """A plain Exception is not retryable."""
        assert _is_retryable_status_error(ValueError("nope")) is False


# ---------------------------------------------------------------------------
# call_with_retry
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestCallWithRetry:
    """Tests for the retry wrapper behavior."""

    async def test_succeeds_first_try(self):
        """Function that succeeds immediately is called once."""
        fn = MagicMock(return_value="ok")
        result = await call_with_retry(fn, max_retries=3)
        assert result == "ok"
        assert fn.call_count == 1

    async def test_succeeds_after_retries(self):
        """Function that fails twice then succeeds returns the result."""
        fn = MagicMock(side_effect=[ConnectionError("fail"), ConnectionError("fail"), "ok"])
        with patch("api.clients.retry.asyncio.sleep", new_callable=AsyncMock):
            result = await call_with_retry(fn, max_retries=3, base_delay=0.01)
        assert result == "ok"
        assert fn.call_count == 3

    async def test_exhausts_retries(self):
        """Function that always fails raises after max_retries + 1 attempts."""
        fn = MagicMock(side_effect=ConnectionError("always fail"))
        with patch("api.clients.retry.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(ConnectionError, match="always fail"):
                await call_with_retry(fn, max_retries=2, base_delay=0.01)
        assert fn.call_count == 3  # initial + 2 retries

    async def test_non_retryable_raises_immediately(self):
        """Non-retryable error is raised without retrying."""
        fn = MagicMock(side_effect=ValueError("bad input"))
        with pytest.raises(ValueError, match="bad input"):
            await call_with_retry(fn, max_retries=3)
        assert fn.call_count == 1

    async def test_handles_coroutine_result(self):
        """Awaits coroutine results from the wrapped function."""
        async def async_fn():
            return "async ok"
        fn = MagicMock(side_effect=lambda: async_fn())
        result = await call_with_retry(fn, max_retries=1)
        assert result == "async ok"
