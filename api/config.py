"""
Application Configuration Settings

This module defines the configuration settings for the workflow automation system.
It loads environment variables and provides default values for all configurable parameters.

Environment Variables:
    ANTHROPIC_API_KEY: API key for Anthropic Claude AI service
    LIGHTON_API_KEY: API key for LightOn Paradigm service
    DEBUG: Enable debug mode (true/false)
    HOST: Server host address (default: 0.0.0.0)
    PORT: Server port number (default: 8000)

Features:
    - Environment variable loading via python-dotenv
    - Configuration validation
    - Default values for all settings
    - LightOn Paradigm API endpoint configuration
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Find .env file in project root (parent directory of api/)
env_path = Path(__file__).parent.parent / '.env'

# Load environment variables from .env file
# override=True ensures .env file values take precedence
load_dotenv(dotenv_path=env_path, override=True)

class Settings:
    """
    Application settings configuration class.
    
    Loads configuration from environment variables and provides validation.
    All settings have sensible defaults and can be overridden via environment variables.
    """
    
    def __init__(self):
        # Core API keys - required for operation
        self.anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
        self.lighton_api_key: str = os.getenv("LIGHTON_API_KEY", "")

        # Server configuration
        self.debug: bool = os.getenv("DEBUG", "false").lower() == "true"
        self.host: str = os.getenv("HOST", "0.0.0.0")
        self.port: int = int(os.getenv("PORT", "8000"))

        # Environment detection (Vercel sets VERCEL=1)
        self.is_vercel: bool = os.getenv("VERCEL", "").lower() in ["1", "true"]
        
        # LightOn Paradigm API settings
        # v2 endpoints for file operations (upload, get, delete, chunks)
        self.lighton_base_url: str = "https://paradigm.lighton.ai"
        self.lighton_docsearch_endpoint: str = "/api/v2/chat/document-search"

        # v3 Agent API endpoint for unified threads/turns interface
        self.lighton_v3_base_url: str = "https://paradigm.lighton.ai"
        self.lighton_v3_agent_endpoint: str = "/api/v3/threads/turns"

        # v3 Agent API requires chat_setting_id (user's agent configuration)
        self.lighton_chat_setting_id: int = int(os.getenv("LIGHTON_CHAT_SETTING_ID", "160"))
        
        # Workflow execution settings
        self.max_execution_time: int = 1800  # 20 minutes maximum execution time
        self.max_workflow_steps: int = 50   # Maximum number of workflow steps

        # LLM Configuration (Anthropic)
        self.anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        self.anthropic_timeout: float = float(os.getenv("ANTHROPIC_TIMEOUT", "120"))
        self.anthropic_max_tokens_cell: int = int(os.getenv("ANTHROPIC_MAX_TOKENS_CELL", "16000"))
        self.anthropic_max_tokens_plan: int = int(os.getenv("ANTHROPIC_MAX_TOKENS_PLAN", "8000"))
        
    def validate(self) -> None:
        """
        Validate that required settings are present.
        
        Raises:
            ValueError: If any required API key is missing
        """
        if not self.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required")
        if not self.lighton_api_key:
            raise ValueError("LIGHTON_API_KEY is required")

# Global settings instance - used throughout the application
settings = Settings()