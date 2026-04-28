"""
Web App Gateway
================

Multi-tenant gateway that exposes saved workflows as small standalone web
apps served at ``/app/{workflow_id}/``. The same backend that runs the
Workflow Builder UI also serves these per-workflow runners, reusing:

  - ``executable.compile_workflow`` to keep the workflow's code compiled and
    warm in the same process as the MCP gateway,
  - ``analyze_workflow_for_ui`` and ``generate_simple_description`` from the
    existing package-generation pipeline (called ONCE at deploy time and
    cached, so re-clicks are cheap and deterministic),
  - the ``frontend_index.html`` + ``backend_main.py`` templates already shipped
    in ``api/workflow/templates/workflow_runner/``.

Critically, the downloadable ZIP from ``/api/workflow/generate-package`` is
re-routed to look up the cached registration here, so the live web app and
the ZIP always carry the same workflow code + UI config.
"""

import io
import json
import logging
import re
import secrets
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import UploadFile

from .. import paradigm_client as _paradigm_client_module
from ..config import settings
from .core.executor import redis_client
from .executable import build_combined_code, compile_workflow

logger = logging.getLogger(__name__)

_REG_KEY_PREFIX = "web_registration:"
_REG_TTL_SECONDS = 30 * 24 * 3600  # 30 days
_TEMPLATES_DIR = Path(__file__).parent / "templates" / "workflow_runner"

# Final-result keys the standalone runner template walks in priority order.
# Mirrored here so the live /app/{id}/execute path returns the same shape.
_FINAL_KEYS = ["final_result", "report", "final_report", "summary", "output", "result", "analysis"]


@dataclass
class WebRegistration:
    """Persistent metadata for a deployed-as-Web-App workflow.

    The ``code`` and ``ui_config`` are stored snapshot-style: re-deploying the
    workflow refreshes them, but a download in between always sees the live
    app's exact materials.
    """
    workflow_id: str
    access_token: str
    workflow_name: str
    workflow_name_slug: str
    workflow_description: str         # the simple description, end-user facing
    code: str                         # combined workflow source
    code_hash: str
    ui_config: Dict[str, Any]         # output of analyze_workflow_for_ui
    created_at: float


def _slugify_url(name: str) -> str:
    s = (name or "workflow").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:50] or "workflow"


def _extract_final_result(result: Any) -> str:
    """Mirror the runner template's result extraction logic.

    Workflows tend to produce dicts whose final cell stores a markdown report
    under one of a few known keys. Surface that string when present; fall back
    to a JSON dump for everything else so nothing is silently dropped.
    """
    if isinstance(result, str):
        return result
    if not isinstance(result, dict):
        return str(result)

    for key in _FINAL_KEYS:
        val = result.get(key)
        if val:
            return val if isinstance(val, str) else json.dumps(val, ensure_ascii=False, default=str)

    # Fallback: last non-trivial string value in the dict
    for key in reversed(list(result.keys())):
        val = result[key]
        if isinstance(val, str) and len(val) > 50:
            return val

    return json.dumps(result, indent=2, ensure_ascii=False, default=str)


class WebGateway:
    """Multi-tenant in-process web app server for deployed workflows."""

    def __init__(self) -> None:
        self._registrations: Dict[str, WebRegistration] = {}

    # ------------------------------------------------------------------
    # Registration storage
    # ------------------------------------------------------------------

    def get_registration(self, workflow_id: str) -> Optional[WebRegistration]:
        cached = self._registrations.get(workflow_id)
        if cached:
            return cached
        if redis_client:
            raw = redis_client.get(_REG_KEY_PREFIX + workflow_id)
            if raw:
                try:
                    data = json.loads(raw) if isinstance(raw, str) else json.loads(raw.decode())
                    reg = WebRegistration(**data)
                    self._registrations[workflow_id] = reg
                    return reg
                except Exception as e:
                    logger.warning("Failed to decode web registration for %s: %s", workflow_id, e)
        return None

    def _save_registration(self, reg: WebRegistration) -> None:
        self._registrations[reg.workflow_id] = reg
        if redis_client:
            try:
                redis_client.setex(
                    _REG_KEY_PREFIX + reg.workflow_id,
                    _REG_TTL_SECONDS,
                    json.dumps(asdict(reg)),
                )
            except Exception as e:
                logger.warning("Failed to persist web registration to Redis: %s", e)

    # ------------------------------------------------------------------
    # Auth (browser-friendly: ?token=... or wf_app_<id> cookie)
    # ------------------------------------------------------------------

    def cookie_name(self, workflow_id: str) -> str:
        return "wf_app_{}".format(workflow_id.replace("-", ""))

    def verify_access(
        self,
        workflow_id: str,
        token_query: Optional[str],
        token_cookie: Optional[str],
    ) -> bool:
        reg = self.get_registration(workflow_id)
        if not reg:
            return False
        for candidate in (token_query, token_cookie):
            if candidate and secrets.compare_digest(candidate, reg.access_token):
                return True
        return False

    # ------------------------------------------------------------------
    # Registration: pre-compute code + UI config and cache them
    # ------------------------------------------------------------------

    async def register(self, workflow_id: str) -> WebRegistration:
        """Compile the workflow, run UI/description analysis, mint an access token.

        Re-clicking deploy refreshes the cached code + UI config and rotates
        the access token (older share links stop working — same semantics as
        the MCP gateway).
        """
        # Imports kept local to avoid pulling Anthropic SDK at module import time.
        from .core.analyzer import analyze_workflow_for_ui, generate_simple_description

        # Compile up-front so a syntax/import error surfaces at button-click,
        # not at the user's first /execute call.
        compiled = compile_workflow(workflow_id)
        code, _ = build_combined_code(workflow_id)  # already cached on the executable side

        try:
            ui_config = await analyze_workflow_for_ui(
                workflow_code=code,
                workflow_name=compiled.workflow_name,
                workflow_description=compiled.workflow_description or "",
            )
        except Exception as e:
            logger.exception("analyze_workflow_for_ui failed for %s", workflow_id)
            raise ValueError("Failed to analyze workflow code for UI: {}".format(e)) from e

        try:
            simple_description = await generate_simple_description(
                workflow_description=compiled.workflow_description or "",
                workflow_name=compiled.workflow_name,
            )
        except Exception as e:
            logger.warning("generate_simple_description failed (using raw): %s", e)
            simple_description = compiled.workflow_description or compiled.workflow_name

        reg = WebRegistration(
            workflow_id=workflow_id,
            access_token=secrets.token_urlsafe(24),
            workflow_name=compiled.workflow_name,
            workflow_name_slug=_slugify_url(compiled.workflow_name),
            workflow_description=simple_description,
            code=code,
            code_hash=compiled.code_hash,
            ui_config=ui_config,
            created_at=time.time(),
        )
        self._save_registration(reg)
        logger.info("Registered web app for workflow %s at /app/%s", workflow_id, workflow_id)
        return reg

    # ------------------------------------------------------------------
    # Live serving
    # ------------------------------------------------------------------

    def render_index_html(self, reg: WebRegistration) -> str:
        """Read the runner template, substitute placeholders, return HTML.

        The template hardcodes ``API_BASE = 'http://localhost:8000'`` for the
        downloadable-ZIP runtime; for the in-process gateway we rewrite it to
        the live ``/app/<id>`` prefix so the existing fetch calls land on our
        routes without any other template change.
        """
        path = _TEMPLATES_DIR / "frontend_index.html"
        html = path.read_text(encoding="utf-8")
        html = html.replace("{{WORKFLOW_NAME}}", reg.workflow_name)
        html = html.replace("{{WORKFLOW_DESCRIPTION}}", reg.workflow_description or "")
        html = html.replace(
            "const API_BASE = 'http://localhost:8000';",
            "const API_BASE = '/app/{}';".format(reg.workflow_id),
        )
        return html

    def render_config_json(self, reg: WebRegistration) -> Dict[str, Any]:
        """Return the cached ui_config exactly as it would ship in the ZIP."""
        return reg.ui_config

    async def upload_and_execute(
        self,
        workflow_id: str,
        user_input: str,
        files: List[UploadFile],
    ) -> Dict[str, Any]:
        """Run the workflow with files uploaded by the browser.

        Mirrors the standalone runner's /execute path so live and ZIP behave
        identically: upload → wait for indexing → execute_workflow → extract
        final result key.
        """
        import asyncio  # local — avoid leaking asyncio at module level

        reg = self.get_registration(workflow_id)
        if not reg:
            raise ValueError("Workflow not deployed as web app")

        compiled = compile_workflow(workflow_id)

        execution_id = "exec_{}".format(uuid.uuid4().hex[:12])
        start = time.time()
        logger.info("[%s] /app/%s/execute starting (input=%s, files=%d)",
                    execution_id, workflow_id, user_input[:60], len(files))

        api_key = settings.lighton_api_key
        if not api_key:
            raise ValueError("LIGHTON_API_KEY not configured on the server")
        paradigm_client = _paradigm_client_module.ParadigmClient(api_key=api_key)

        file_ids: List[int] = []
        try:
            real_files = [f for f in files if f and f.filename]
            if real_files:
                BATCH_SIZE = 6
                for i, file in enumerate(real_files):
                    content = await file.read()
                    upload_result = await paradigm_client.upload_file(
                        file_content=content,
                        filename=file.filename,
                    )
                    fid = upload_result.get("id") or upload_result.get("file_id")
                    if fid is None:
                        raise ValueError("Paradigm upload did not return an id: {}".format(upload_result))
                    file_ids.append(int(fid))
                    logger.info("[%s] uploaded %s -> file_id=%s", execution_id, file.filename, fid)
                    if i < len(real_files) - 1:
                        # Same rate-limit-aware pacing as the standalone runner.
                        if (i + 1) % BATCH_SIZE == 0:
                            await asyncio.sleep(60.0)
                        else:
                            await asyncio.sleep(0.5)

                # Wait for indexing — mirror the runner template's 10s pause.
                # Could be replaced by paradigm_client.wait_for_embedding per id
                # if we want tighter timing later.
                await asyncio.sleep(10)

            result = await compiled.execute_workflow(user_input, file_ids if file_ids else None)
            extracted = _extract_final_result(result)
            elapsed = round(time.time() - start, 2)
            logger.info("[%s] /execute done in %.1fs", execution_id, elapsed)
            return {
                "status": "completed",
                "result": extracted,
                "execution_time": elapsed,
                "execution_id": execution_id,
            }
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            logger.exception("[%s] /execute failed", execution_id)
            return {
                "status": "failed",
                "result": "Workflow execution failed: {}".format(e),
                "execution_time": elapsed,
                "execution_id": execution_id,
            }
        finally:
            try:
                await paradigm_client.close()
            except Exception:
                pass

    async def delete_uploaded_file(self, file_id: int) -> Dict[str, Any]:
        """Best-effort cleanup of a Paradigm file uploaded by this app.

        Frontend may call this after a workflow run. We never raise — failure
        to delete should not block the user's workflow.
        """
        api_key = settings.lighton_api_key
        if not api_key:
            return {"success": False, "message": "API key not configured"}
        client = _paradigm_client_module.ParadigmClient(api_key=api_key)
        try:
            res = await client.delete_file(file_id)
            success = res.get("success", False) if isinstance(res, dict) else bool(res)
            return {"success": success, "message": "File {} deleted".format(file_id)}
        except Exception as e:
            logger.warning("Failed to delete file %s: %s", file_id, e)
            return {"success": False, "message": str(e)}
        finally:
            try:
                await client.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Download: ZIP from the cached registration (NO re-analysis)
    # ------------------------------------------------------------------

    def build_download_zip(self, reg: WebRegistration) -> io.BytesIO:
        """Package the cached registration into the existing ZIP layout.

        This intentionally calls the existing ``WorkflowPackageGenerator``
        with the cached ``code`` and ``ui_config``. No re-analysis, so two
        downloads are byte-identical and always match what's serving live.
        """
        # Local import: pulls a few extra modules we don't need at gateway-only callers.
        from .generators.workflow_package import WorkflowPackageGenerator

        generator = WorkflowPackageGenerator(
            workflow_name=reg.workflow_name,
            workflow_description=reg.workflow_description,
            workflow_code=reg.code,
            ui_config=reg.ui_config,
        )
        return generator.generate_zip()


# Module-level singleton used by the FastAPI routes.
web_gateway = WebGateway()
