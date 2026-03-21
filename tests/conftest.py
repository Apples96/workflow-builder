"""
Pytest configuration for all tests.
"""

import sys
from pathlib import Path

import pytest

# Ensure the project root is on sys.path so `api` is importable
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


collect_ignore = ["simple_paradigm_test.py", "test_api_key.py"]


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: Fast unit tests (no network calls)")
    config.addinivalue_line("markers", "paradigm: Tests pour Paradigm API")
    config.addinivalue_line("markers", "workflow: Tests pour Workflow API")
    config.addinivalue_line("markers", "files: Tests pour Files API")
    config.addinivalue_line("markers", "integration: Tests d'intégration")
    config.addinivalue_line("markers", "security: Tests de sécurité")
    config.addinivalue_line("markers", "slow: Tests lents (> 10 secondes)")


@pytest.fixture(scope="session")
def anyio_backend():
    """Backend for async tests."""
    return "asyncio"


@pytest.fixture(autouse=True)
def _clear_prompt_cache():
    """Clear PromptLoader cache between tests to avoid cross-test leakage."""
    yield
    try:
        from api.workflow.prompts.loader import PromptLoader
        PromptLoader.clear_cache()
    except ImportError:
        pass
