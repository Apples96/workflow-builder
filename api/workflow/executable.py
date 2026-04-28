"""
ExecutableWorkflow registry
===========================

Shared in-process compile-and-cache layer used by both the MCP gateway and the
Web App gateway. A workflow's "deploy as X" action ultimately needs the same
thing: turn the saved cell plan into a callable ``execute_workflow(query,
file_ids)`` and keep it warm in memory.

This module owns:
  - ``CompiledWorkflow``: a frozen handle to the exec'd module namespace plus
    its source-code hash and human-readable metadata.
  - ``compile_workflow(workflow_id)``: idempotent compile-or-reuse using the
    same ``combine_workflow_cells`` path that ``generate-package`` and
    ``generate-mcp-package`` use.
  - The ``paradigm_client`` import shim — registered once at import time so the
    generated cell code's ``from paradigm_client import ParadigmClient`` line
    resolves to the *full* backend client (not the lighter standalone copy
    bundled with the downloadable ZIP).
"""

import hashlib
import logging
import os
import re
import sys
from dataclasses import dataclass
from typing import Any, Callable, Dict, Tuple

from .. import paradigm_client as _paradigm_client_module
# Pin the import name BEFORE any combined workflow code gets exec'd. We
# deliberately use the full client (not paradigm_client_standalone) so the
# in-process gateways match the UI's /execute-stream path exactly — same
# retries, same kwargs, same behavior. The standalone client is reserved for
# the downloadable ZIP, which runs out of process.
sys.modules["paradigm_client"] = _paradigm_client_module

from ..config import settings
from .cell.combiner import combine_workflow_cells
from .core.executor import workflow_executor

logger = logging.getLogger(__name__)


@dataclass
class CompiledWorkflow:
    """Frozen handle to an exec'd workflow module."""
    workflow_id: str
    code: str                    # the full combined source as fed to exec()
    code_hash: str               # sha256(code)
    namespace: Dict[str, Any]    # module globals after exec()
    execute_workflow: Callable   # awaitable: (user_input: str, file_ids: Optional[List[int]]) -> dict
    workflow_name: str
    workflow_description: str


# Process-wide cache. Keyed by workflow_id. Every entry has a code_hash;
# callers must compare it against the freshly-built combined code to detect
# stale compiles after a workflow is re-edited.
_COMPILE_CACHE: Dict[str, CompiledWorkflow] = {}


def slugify(name: str) -> str:
    """Slugify a workflow name into something safe for tool names + URLs."""
    s = (name or "workflow").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:60] or "workflow"


def _ensure_paradigm_env() -> None:
    """Make sure LIGHTON_API_KEY is set so the combined code's top-level guard
    does not raise inside exec()."""
    if os.environ.get("LIGHTON_API_KEY") or os.environ.get("PARADIGM_API_KEY"):
        return
    if settings.lighton_api_key:
        os.environ["LIGHTON_API_KEY"] = settings.lighton_api_key
        return
    raise ValueError(
        "LIGHTON_API_KEY is not configured on the server. Set it as an environment "
        "variable before deploying a workflow."
    )


def build_combined_code(workflow_id: str) -> Tuple[str, Any]:
    """Resolve the workflow and return ``(combined_code, workflow)``.

    Mirrors the path used by ``/api/workflow/generate-package`` and
    ``/api/workflow/generate-mcp-package``: prefer the workflow's pre-combined
    ``generated_code`` if present, otherwise rebuild from the cell plan.
    """
    workflow = workflow_executor.get_workflow(workflow_id)
    if not workflow:
        raise ValueError("Workflow not found: {}".format(workflow_id))

    code = workflow.generated_code
    if not code:
        plan = workflow_executor.get_workflow_plan(workflow_id)
        if not plan or not plan.cells:
            raise ValueError(
                "Workflow has no plan with cells. Run the workflow at least once before deploying."
            )
        if not any(c.generated_code for c in plan.cells):
            raise ValueError(
                "Workflow cells have no generated code yet. Run the workflow at least once before deploying."
            )
        code = combine_workflow_cells(
            plan=plan,
            workflow_description=workflow.description or "",
        )

    return code, workflow


def compile_workflow(workflow_id: str) -> CompiledWorkflow:
    """Compile (or reuse a cached compile of) the workflow's combined code.

    Re-runs exec() if the source changed since last compile; otherwise returns
    the cached entry. Callers should always go through this helper rather than
    holding their own ``CompiledWorkflow`` references — that way both the MCP
    gateway and the web gateway stay in sync if the workflow gets re-edited.
    """
    code, workflow = build_combined_code(workflow_id)
    code_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()

    cached = _COMPILE_CACHE.get(workflow_id)
    if cached and cached.code_hash == code_hash:
        return cached

    # Belt-and-suspenders: re-pin the import shim in case anything cleared it.
    sys.modules["paradigm_client"] = _paradigm_client_module
    _ensure_paradigm_env()

    # Fresh per-workflow namespace so cell-level globals (cell_xxx fns,
    # helpers) don't collide across deployed workflows. Omitting __builtins__
    # lets exec() populate it correctly automatically.
    namespace: Dict[str, Any] = {"__name__": "workflow_exec_{}".format(workflow_id)}
    try:
        compiled_obj = compile(code, "<workflow_{}>".format(workflow_id), "exec")
        exec(compiled_obj, namespace)
    except Exception as e:
        logger.exception("Failed to compile combined workflow code for %s", workflow_id)
        raise ValueError("Failed to compile workflow code: {}".format(e)) from e

    execute_workflow = namespace.get("execute_workflow")
    if not callable(execute_workflow):
        raise ValueError("Combined workflow code did not define execute_workflow().")

    compiled = CompiledWorkflow(
        workflow_id=workflow_id,
        code=code,
        code_hash=code_hash,
        namespace=namespace,
        execute_workflow=execute_workflow,
        workflow_name=workflow.name or "Unnamed Workflow",
        workflow_description=workflow.description or "",
    )
    _COMPILE_CACHE[workflow_id] = compiled
    return compiled


def get_cached(workflow_id: str) -> CompiledWorkflow:
    """Return the cached compile, raising KeyError if not present.

    Useful for routes that should NEVER recompile (e.g. the live /execute path
    after a deploy has explicitly happened). Most callers should use
    ``compile_workflow`` instead, which falls back to recompile.
    """
    return _COMPILE_CACHE[workflow_id]
