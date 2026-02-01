"""
Retry Logic for API Calls

This module provides retry functionality with exponential backoff for
handling transient failures in API calls. It supports both Anthropic
and Paradigm API error types.

Features:
    - Exponential backoff with jitter
    - Configurable retry counts and delays
    - Support for both sync and async functions
    - Specific handling for rate limits, connection errors, and server errors

Usage:
    from api.clients import call_with_retry

    # Async usage
    result = await call_with_retry(
        lambda: client.messages.create(...),
        max_retries=3
    )

    # With Paradigm client
    result = await call_with_retry(
        lambda: paradigm_client.agent_query(...),
        max_retries=3
    )
"""

import asyncio
import logging
import random
from typing import Any, Callable, Tuple, TypeVar, Union

# Import Anthropic error types
try:
    from anthropic import (
        APIConnectionError,
        RateLimitError,
        APIStatusError,
        InternalServerError,
    )
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

# Import aiohttp for Paradigm errors
try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

logger = logging.getLogger(__name__)

T = TypeVar('T')

# Default retryable error types
DEFAULT_RETRYABLE_ERRORS: Tuple[type, ...] = (
    ConnectionError,
    TimeoutError,
)

# Add Anthropic errors if available
if HAS_ANTHROPIC:
    DEFAULT_RETRYABLE_ERRORS = DEFAULT_RETRYABLE_ERRORS + (
        APIConnectionError,
        RateLimitError,
        InternalServerError,
    )

# Add aiohttp errors if available
if HAS_AIOHTTP:
    DEFAULT_RETRYABLE_ERRORS = DEFAULT_RETRYABLE_ERRORS + (
        aiohttp.ClientError,
        aiohttp.ServerTimeoutError,
    )


def _is_retryable_status_error(error: Exception) -> bool:
    """
    Check if an APIStatusError has a retryable status code.

    Args:
        error: The exception to check

    Returns:
        bool: True if the error is retryable
    """
    if HAS_ANTHROPIC and isinstance(error, APIStatusError):
        # Retry on 429 (rate limit), 500, 502, 503, 504 (server errors)
        return error.status_code in (429, 500, 502, 503, 504)
    return False


async def call_with_retry(
    func: Callable[[], Union[T, Any]],
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    retryable_errors: Tuple[type, ...] = None,
    operation_name: str = "API call"
) -> T:
    """
    Call a function with exponential backoff on transient errors.

    This function wraps an API call and automatically retries it on
    transient failures like network errors, rate limits, and server errors.

    Args:
        func: The function to call (can be sync or async, or a lambda)
        max_retries: Maximum number of retry attempts (default: 3)
        base_delay: Initial delay in seconds between retries (default: 1.0)
        max_delay: Maximum delay between retries (default: 60.0)
        retryable_errors: Tuple of exception types to retry on
        operation_name: Name of the operation for logging (default: "API call")

    Returns:
        The result of the function call

    Raises:
        The last exception if all retries are exhausted
    """
    if retryable_errors is None:
        retryable_errors = DEFAULT_RETRYABLE_ERRORS

    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            # Call the function
            result = func()

            # Handle coroutines (async functions)
            if asyncio.iscoroutine(result):
                result = await result

            # Success - return the result
            if attempt > 0:
                logger.info("{} succeeded on attempt {}".format(
                    operation_name, attempt + 1
                ))
            return result

        except retryable_errors as e:
            last_exception = e
            _handle_retry(
                e, attempt, max_retries, base_delay, max_delay, operation_name
            )

        except Exception as e:
            # Check for retryable status errors
            if _is_retryable_status_error(e):
                last_exception = e
                _handle_retry(
                    e, attempt, max_retries, base_delay, max_delay, operation_name
                )
            else:
                # Non-retryable error - raise immediately
                raise

        # Wait before retrying (with exponential backoff + jitter)
        if attempt < max_retries:
            delay = _calculate_delay(attempt, base_delay, max_delay)
            logger.info("{} retry {}/{} in {:.2f}s".format(
                operation_name, attempt + 1, max_retries, delay
            ))
            await asyncio.sleep(delay)

    # All retries exhausted
    logger.error("{} failed after {} attempts".format(
        operation_name, max_retries + 1
    ))
    raise last_exception


def _handle_retry(
    error: Exception,
    attempt: int,
    max_retries: int,
    base_delay: float,
    max_delay: float,
    operation_name: str
) -> None:
    """
    Handle a retryable error by logging and preparing for retry.

    Args:
        error: The exception that occurred
        attempt: Current attempt number (0-indexed)
        max_retries: Maximum retry attempts
        base_delay: Base delay for backoff calculation
        max_delay: Maximum delay cap
        operation_name: Name of the operation for logging
    """
    error_type = type(error).__name__

    if attempt >= max_retries:
        logger.error("{} failed after {} attempts: {} - {}".format(
            operation_name, attempt + 1, error_type, str(error)
        ))
    else:
        logger.warning("{} attempt {} failed ({}), will retry: {}".format(
            operation_name, attempt + 1, error_type, str(error)[:200]
        ))


def _calculate_delay(attempt: int, base_delay: float, max_delay: float) -> float:
    """
    Calculate the delay before the next retry attempt.

    Uses exponential backoff with jitter to prevent thundering herd.

    Args:
        attempt: Current attempt number (0-indexed)
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds

    Returns:
        float: Delay in seconds before next retry
    """
    # Exponential backoff: base_delay * 2^attempt
    delay = base_delay * (2 ** attempt)

    # Add jitter (10-30% random variation)
    jitter = delay * random.uniform(0.1, 0.3)
    delay = delay + jitter

    # Cap at max_delay
    return min(delay, max_delay)
