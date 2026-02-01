"""
Anthropic Client Factory

This module provides a centralized factory function for creating Anthropic
clients with consistent configuration across the application.

Features:
    - Consistent timeout configuration
    - Single point of configuration for all Anthropic clients
    - Uses settings for API key and timeout values

Usage:
    from api.clients import create_anthropic_client

    client = create_anthropic_client()
    response = client.messages.create(...)
"""

import httpx
from anthropic import Anthropic
from ..config import settings


def create_anthropic_client() -> Anthropic:
    """
    Create an Anthropic client with standard configuration.

    Uses settings for API key and timeout values to ensure consistent
    configuration across all modules that need to call the Anthropic API.

    Returns:
        Anthropic: Configured Anthropic client instance

    Raises:
        ValueError: If ANTHROPIC_API_KEY is not configured
    """
    if not settings.anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY is not configured")

    return Anthropic(
        api_key=settings.anthropic_api_key,
        timeout=httpx.Timeout(settings.anthropic_timeout, connect=10.0)
    )
