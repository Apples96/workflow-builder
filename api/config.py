"""
Application Configuration Settings

Loads environment variables from .env and provides defaults for all
configurable parameters (API keys, server settings, LLM config).
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

        # Public base URL of the running server (e.g. https://workflowbuilder.onrender.com).
        # Used to build absolute MCP server URLs we hand back to the user when they deploy
        # a workflow as an MCP server. Falls back to request.base_url when unset.
        self.public_base_url: str = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
        
        # LightOn Paradigm API settings
        self.lighton_base_url: str = "https://paradigm.lighton.ai"
        self.lighton_v3_base_url: str = "https://paradigm.lighton.ai"
        self.lighton_v3_agent_endpoint: str = "/api/v3/threads/turns"
        self.lighton_chat_setting_id: int = int(os.getenv("LIGHTON_CHAT_SETTING_ID", "160"))
        self.lighton_agent_id: int = int(os.getenv("LIGHTON_AGENT_ID", "0"))  # 0 means auto-discover
        self.paradigm_model: str = os.getenv("PARADIGM_MODEL", "alfred-ft5")
        self.paradigm_timeout: int = int(os.getenv("PARADIGM_TIMEOUT", "300"))

        # Workflow execution settings
        self.max_execution_time: int = 1800  # 20 minutes maximum execution time
        self.max_cell_execution_time: int = int(os.getenv("MAX_CELL_EXECUTION_TIME", "300"))
        self.max_retry_attempts: int = int(os.getenv("MAX_RETRY_ATTEMPTS", "5"))
        self.max_evaluation_retries: int = int(os.getenv("MAX_EVALUATION_RETRIES", "5"))
        self.min_evaluation_score_to_proceed: float = float(os.getenv("MIN_EVALUATION_SCORE_TO_PROCEED", "0.6"))
        self.eval_output_max_chars: int = int(os.getenv("EVAL_OUTPUT_MAX_CHARS", "4000"))

        # LLM Configuration (Anthropic)
        self.anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        self.anthropic_timeout: float = float(os.getenv("ANTHROPIC_TIMEOUT", "120"))
        self.anthropic_max_tokens_cell: int = int(os.getenv("ANTHROPIC_MAX_TOKENS_CELL", "16000"))
        self.anthropic_max_tokens_plan: int = int(os.getenv("ANTHROPIC_MAX_TOKENS_PLAN", "16000"))
        
    def validate(self) -> None:
        """
        Validate that required settings are present.

        Only ANTHROPIC_API_KEY is required server-side (paid by LightOn).
        LIGHTON_API_KEY is optional here — users provide their own via the frontend.

        Raises:
            ValueError: If ANTHROPIC_API_KEY is missing
        """
        if not self.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required")

# Global settings instance - used throughout the application
settings = Settings()