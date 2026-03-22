import httpx
from anthropic import Anthropic
from ..config import settings

# Singleton client instance — reuses HTTP connection pool across all callers
_shared_client = None


def create_anthropic_client() -> Anthropic:
    """Return a shared Anthropic client, creating it on first call.

    Reuses a single HTTP connection pool instead of creating a new client
    per generator/evaluator/planner instance.
    """
    global _shared_client
    if _shared_client is not None:
        return _shared_client

    if not settings.anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY is not configured")

    _shared_client = Anthropic(
        api_key=settings.anthropic_api_key,
        timeout=httpx.Timeout(settings.anthropic_timeout, connect=10.0)
    )
    return _shared_client
