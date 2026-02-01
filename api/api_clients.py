"""
API Clients Re-Export Module (Backward Compatibility Layer)

This module re-exports API client functionality from the refactored modules:
- anthropic_client.py: Anthropic Claude API functions
- paradigm_client.py: LightOn Paradigm API functions and client class

All existing imports continue to work:
    from .api_clients import paradigm_client
    from .api_clients import anthropic_generate_code

For new code, prefer importing directly from the specific modules:
    from .anthropic_client import anthropic_generate_code
    from .paradigm_client import ParadigmClient
"""

# ============================================================================
# ANTHROPIC API RE-EXPORTS
# ============================================================================

from .anthropic_client import (
    clean_json_response,
    anthropic_generate_code,
    anthropic_chat_completion,
    AnthropicClient,
)

# ============================================================================
# PARADIGM API RE-EXPORTS
# ============================================================================

from .paradigm_client import (
    # Main class
    ParadigmClient,
    # Global instance
    paradigm_client,
    # Helper function
    _extract_v3_answer,
    # v3 Agent API functions
    agent_query,
    # v2 File operations
    paradigm_upload_file,
    paradigm_get_file,
    paradigm_get_file_info,
    paradigm_get_file_chunks,
    paradigm_delete_file,
    paradigm_wait_for_embedding,
    # v2 Search/Query operations
    paradigm_filter_chunks,
    paradigm_query,
    paradigm_document_search,
    paradigm_search_with_vision_fallback,
)

# ============================================================================
# BACKWARD COMPATIBILITY ALIASES
# ============================================================================

# Alias classes for backward compatibility
MockAnthropicClient = AnthropicClient
MockParadigmClient = ParadigmClient

# Create global instances for backward compatibility
anthropic_client = AnthropicClient()

# ============================================================================
# MODULE EXPORTS
# ============================================================================

__all__ = [
    # JSON utilities
    'clean_json_response',
    # Anthropic functions
    'anthropic_generate_code',
    'anthropic_chat_completion',
    'AnthropicClient',
    'MockAnthropicClient',  # Backward compat alias
    'anthropic_client',
    # Paradigm class and instance
    'ParadigmClient',
    'MockParadigmClient',  # Backward compat alias
    'paradigm_client',
    # v3 Agent API
    '_extract_v3_answer',
    'agent_query',
    # v2 File operations
    'paradigm_upload_file',
    'paradigm_get_file',
    'paradigm_get_file_info',
    'paradigm_get_file_chunks',
    'paradigm_delete_file',
    'paradigm_wait_for_embedding',
    # v2 Search/Query
    'paradigm_filter_chunks',
    'paradigm_query',
    'paradigm_document_search',
    'paradigm_search_with_vision_fallback',
]
