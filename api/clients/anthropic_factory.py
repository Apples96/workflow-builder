import httpx
from anthropic import Anthropic
from ..config import settings


def create_anthropic_client() -> Anthropic:
    """Create an Anthropic client with standard configuration."""
    if not settings.anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY is not configured")

    return Anthropic(
        api_key=settings.anthropic_api_key,
        timeout=httpx.Timeout(settings.anthropic_timeout, connect=10.0)
    )
