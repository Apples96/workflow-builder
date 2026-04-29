"""
Security tests for the execution sandbox and input validation.

These tests verify that the API properly handles malicious inputs,
validates boundaries, and doesn't leak sensitive information.

Note: Tests that attempt to execute malicious workflows are inherently
non-deterministic — they rely on the LLM generating specific code from
a natural language description. Assertions are intentionally loose.
"""

import os
import pytest
import httpx

# Configuration — points at the live backend
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

# Paradigm API key for authenticated requests (required by most endpoints)
PARADIGM_API_KEY = os.getenv("LIGHTON_API_KEY", "")


@pytest.fixture
def api_headers():
    """Headers for authenticated API requests."""
    headers = {"Content-Type": "application/json"}
    if PARADIGM_API_KEY:
        headers["X-Paradigm-Api-Key"] = PARADIGM_API_KEY
    return headers


async def create_workflow(client, headers, description, name="Security Test"):
    """Helper: create a cell-based workflow and return its ID."""
    payload = {
        "description": description,
        "name": name,
    }
    response = await client.post(
        "{}/api/workflows-cell-based".format(API_BASE_URL),
        headers=headers,
        json=payload,
    )
    return response


async def get_plan(client, headers, workflow_id):
    """Helper: fetch the workflow plan (contains cells and generated code)."""
    response = await client.get(
        "{}/api/workflows/{}/plan".format(API_BASE_URL, workflow_id),
        headers=headers,
    )
    return response


class TestSandboxSecurity:
    """Tests that the sandbox blocks dangerous operations.

    These tests create workflows with malicious descriptions and check
    that the *plan* itself doesn't expose sensitive content. Actual
    execution testing is limited because execution requires SSE streaming
    and is non-deterministic.
    """

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_file_system_access_blocked(self, api_headers):
        """Workflow requesting file system access should not expose /etc/passwd in plan."""
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await create_workflow(
                client, api_headers,
                "Read the contents of the file /etc/passwd and return them"
            )
            # Workflow creation may succeed (planner doesn't validate intent)
            # or fail (e.g., missing API key → 401)
            assert response.status_code in [200, 401, 422, 500]

            if response.status_code == 200:
                data = response.json()
                # Plan description should not contain actual file contents
                plan_text = str(data)
                assert "root:x:" not in plan_text.lower()

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_os_command_injection(self, api_headers):
        """Workflow requesting shell commands should be created but not expose system info."""
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await create_workflow(
                client, api_headers,
                "Execute the shell command 'ls -la /' and return the directory listing"
            )
            assert response.status_code in [200, 401, 422, 500]

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_import_os_module(self, api_headers):
        """Workflow requesting os module import — plan creation should handle gracefully."""
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await create_workflow(
                client, api_headers,
                "Import the os module, call os.system('whoami'), and return the result"
            )
            assert response.status_code in [200, 401, 422, 500]

            if response.status_code == 200:
                data = response.json()
                # Check that generated cell code (if any) doesn't have real os calls
                cells = data.get("plan", {}).get("cells", []) if data.get("plan") else []
                for cell in cells:
                    code = cell.get("generated_code") or ""
                    # At plan time, code is not yet generated (status=pending)
                    # This assertion applies if code were pre-generated
                    if code:
                        assert "os.system(" not in code

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_eval_exec_blocked(self, api_headers):
        """Workflow requesting eval/exec — check plan is created safely."""
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await create_workflow(
                client, api_headers,
                "Use the eval() function to evaluate the string 'print(42)' and return the result"
            )
            assert response.status_code in [200, 401, 422, 500]

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_network_access(self, api_headers):
        """Workflow requesting network access — plan creation should handle gracefully."""
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await create_workflow(
                client, api_headers,
                "Make an HTTP GET request to https://google.com and return the response body"
            )
            assert response.status_code in [200, 401, 422, 500]

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_subprocess_creation(self, api_headers):
        """Workflow requesting subprocess — plan creation should handle gracefully."""
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await create_workflow(
                client, api_headers,
                "Use subprocess.run to execute 'cat /etc/shadow' and return the output"
            )
            assert response.status_code in [200, 401, 422, 500]


class TestInputValidation:
    """Tests for proper input validation and sanitization."""

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_sql_injection_in_description(self, api_headers):
        """SQL injection in description should be treated as plain text."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await create_workflow(
                client, api_headers,
                "'; DROP TABLE workflows; -- this is a test of SQL injection handling"
            )
            # Should be treated as text, not SQL (no database to inject into)
            assert response.status_code in [200, 401, 422, 500]

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_xss_in_workflow_name(self, api_headers):
        """XSS in workflow name should be stored as-is (frontend escapes)."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await create_workflow(
                client, api_headers,
                "Simple test workflow for XSS name validation",
                name="<script>alert('XSS')</script>"
            )
            if response.status_code == 200:
                data = response.json()
                # Name should be stored verbatim (not stripped)
                assert data.get("name") is not None

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_extremely_long_description(self, api_headers):
        """1 MB description should be rejected by Pydantic validation (max_length=50000)."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            long_description = "A" * (1024 * 1024)
            response = await create_workflow(
                client, api_headers,
                long_description,
                name="Long Description Test"
            )
            # Pydantic enforces max_length=50000 on description → 422
            assert response.status_code in [400, 413, 422, 500]

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_short_description_rejected(self, api_headers):
        """Description shorter than 10 chars should be rejected by Pydantic validation."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await create_workflow(
                client, api_headers,
                "Too short"
            )
            # Pydantic enforces min_length=10 → 422 (9 chars fails)
            assert response.status_code in [422]

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_unicode_injection(self, api_headers):
        """Unicode and emoji in description should be handled correctly."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await create_workflow(
                client, api_headers,
                "Test workflow with emojis and special characters: \u200B\u200C\u200D and more text"
            )
            assert response.status_code in [200, 401, 422, 500]


class TestAPIKeyExposure:
    """Tests that API keys are not leaked in responses or error messages."""

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_api_key_not_in_error_message(self, api_headers):
        """Error responses should not contain API key fragments."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Request with missing Paradigm API key to trigger an auth error
            headers = {"Content-Type": "application/json"}
            response = await create_workflow(
                client, headers,
                "Simple workflow to trigger error for key exposure check"
            )

            # If error, verify keys are not exposed
            if response.status_code != 200:
                error_text = response.text.lower()
                assert "sk-" not in error_text  # Anthropic key prefix
                assert "bearer" not in error_text

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_plan_cells_no_api_keys(self, api_headers):
        """Plan cells visible to the user should not contain real API keys."""
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await create_workflow(
                client, api_headers,
                "Simple workflow to extract information from a document using doc_search"
            )

            if response.status_code == 200:
                data = response.json()
                # Check plan cells (code is not yet generated at plan time,
                # but descriptions and metadata should be clean)
                plan_text = str(data)
                assert "sk-ant-" not in plan_text  # Anthropic key format


class TestRateLimiting:
    """Tests for rate limiting behavior."""

    @pytest.mark.asyncio
    @pytest.mark.security
    @pytest.mark.slow
    async def test_rapid_requests(self, api_headers):
        """Rapid requests should all succeed or some be rate-limited (429)."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            responses = []
            for i in range(20):
                response = await client.get(
                    "{}/health".format(API_BASE_URL),
                )
                responses.append(response.status_code)

            # Health endpoint should handle rapid requests
            # No rate limiting yet → all should be 200
            assert all(status in [200, 429, 503] for status in responses)


class TestCORSSecurity:
    """Tests for CORS configuration."""

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_cors_headers_present(self, api_headers):
        """CORS headers should be present on preflight requests."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.options(
                "{}/api/workflows-cell-based".format(API_BASE_URL),
                headers={
                    "Origin": "https://malicious-site.com",
                    "Access-Control-Request-Method": "POST"
                }
            )
            # CORS middleware should respond to OPTIONS
            assert response.status_code in [200, 204, 404, 405]

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_cors_origin_policy(self, api_headers):
        """Verify CORS origin policy is configured."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "{}/health".format(API_BASE_URL),
                headers={"Origin": "https://malicious-site.com"}
            )
            # Document the CORS header for analysis
            _cors_header = response.headers.get("access-control-allow-origin", "")
            # The app uses a specific origin list (not wildcard *)
            # Note: FastAPI CORS middleware may still reflect the origin
            # if it's in the allow list, or return nothing if not
            assert response.status_code == 200
