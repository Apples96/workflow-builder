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
    """Check if an APIStatusError has a retryable status code."""
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
    """Call a function with exponential backoff on transient errors."""
    if retryable_errors is None:
        retryable_errors = DEFAULT_RETRYABLE_ERRORS

    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            result = func()
            if asyncio.iscoroutine(result):
                result = await result

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
            if _is_retryable_status_error(e):
                last_exception = e
                _handle_retry(
                    e, attempt, max_retries, base_delay, max_delay, operation_name
                )
            else:
                raise

        if attempt < max_retries:
            delay = _calculate_delay(attempt, base_delay, max_delay)
            logger.info("{} retry {}/{} in {:.2f}s".format(
                operation_name, attempt + 1, max_retries, delay
            ))
            await asyncio.sleep(delay)

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
    """Log a retryable error and prepare for retry."""
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
    """Calculate delay with exponential backoff and jitter."""
    delay = base_delay * (2 ** attempt)
    jitter = delay * random.uniform(0.1, 0.3)
    return min(delay + jitter, max_delay)
