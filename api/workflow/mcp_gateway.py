"""
MCP Gateway
===========

In-process multi-tenant gateway that exposes saved workflows as MCP-over-HTTP
endpoints. The same backend that runs the Workflow Builder UI also serves
``/mcp/{workflow_id}/...`` so Paradigm (or any HTTP MCP client) can invoke a
workflow as an external tool, without spinning up a per-workflow service.

Compilation + in-process exec lives in ``executable.py``. This module is just
the MCP-shaped wrapper: registration, bearer-token auth, MCP tool descriptor.
"""

import json
import logging
import secrets
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

from .core.executor import redis_client
from .executable import compile_workflow, slugify

logger = logging.getLogger(__name__)

_REG_KEY_PREFIX = "mcp_registration:"
_REG_TTL_SECONDS = 30 * 24 * 3600  # 30 days


@dataclass
class Registration:
    """Persistent metadata for a deployed-as-MCP workflow."""
    workflow_id: str
    bearer_token: str
    tool_name: str
    workflow_name: str
    workflow_description: str
    code_hash: str
    created_at: float


class MCPGateway:
    """Multi-tenant in-process MCP server for deployed workflows."""

    def __init__(self) -> None:
        self._registrations: Dict[str, Registration] = {}

    def get_registration(self, workflow_id: str) -> Optional[Registration]:
        cached = self._registrations.get(workflow_id)
        if cached:
            return cached
        if redis_client:
            raw = redis_client.get(_REG_KEY_PREFIX + workflow_id)
            if raw:
                try:
                    data = json.loads(raw) if isinstance(raw, str) else json.loads(raw.decode())
                    reg = Registration(**data)
                    self._registrations[workflow_id] = reg
                    return reg
                except Exception as e:
                    logger.warning("Failed to decode MCP registration for %s: %s", workflow_id, e)
        return None

    def _save_registration(self, reg: Registration) -> None:
        self._registrations[reg.workflow_id] = reg
        if redis_client:
            try:
                redis_client.setex(
                    _REG_KEY_PREFIX + reg.workflow_id,
                    _REG_TTL_SECONDS,
                    json.dumps(asdict(reg)),
                )
            except Exception as e:
                logger.warning("Failed to persist MCP registration to Redis: %s", e)

    def verify_bearer(self, workflow_id: str, authorization: Optional[str]) -> bool:
        reg = self.get_registration(workflow_id)
        if not reg or not authorization:
            return False
        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return False
        return secrets.compare_digest(parts[1], reg.bearer_token)

    def register(self, workflow_id: str) -> Registration:
        """Compile the workflow and mint a fresh bearer token."""
        compiled = compile_workflow(workflow_id)
        token = secrets.token_urlsafe(32)
        reg = Registration(
            workflow_id=workflow_id,
            bearer_token=token,
            tool_name=slugify(compiled.workflow_name),
            workflow_name=compiled.workflow_name,
            workflow_description=compiled.workflow_description,
            code_hash=compiled.code_hash,
            created_at=time.time(),
        )
        self._save_registration(reg)
        logger.info("Registered MCP workflow %s as tool '%s'", workflow_id, reg.tool_name)
        return reg

    async def execute(self, workflow_id: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the deployed workflow with Paradigm-shaped arguments."""
        reg = self.get_registration(workflow_id)
        if not reg:
            raise ValueError("Workflow {} is not deployed as MCP".format(workflow_id))

        compiled = compile_workflow(workflow_id)  # idempotent; recompiles if code changed

        query = arguments.get("query") or arguments.get("user_input") or ""
        raw_file_ids = arguments.get("file_ids")
        file_ids = [int(f) for f in raw_file_ids] if raw_file_ids else None

        return await compiled.execute_workflow(query, file_ids)

    def tool_definition(self, workflow_id: str) -> Dict[str, Any]:
        """Return the MCP tool descriptor for ``GET /mcp/{id}/tools``."""
        reg = self.get_registration(workflow_id)
        if not reg:
            raise KeyError(workflow_id)
        description = (reg.workflow_description or reg.workflow_name).strip()
        return {
            "name": reg.tool_name,
            "description": (
                "{desc}\n\n"
                "Runs a LightOn Workflow Builder workflow as an MCP tool.\n\n"
                "Input parameters:\n"
                "- query (required): user instruction or question to drive the workflow\n"
                "- file_ids (optional): list of Paradigm document IDs to feed into the workflow"
            ).format(desc=description),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "User instruction or question",
                    },
                    "file_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Paradigm document IDs to process",
                    },
                },
                "required": ["query"],
            },
        }


# Module-level singleton used by the FastAPI routes.
mcp_gateway = MCPGateway()
