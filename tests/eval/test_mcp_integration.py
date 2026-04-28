#!/usr/bin/env python3
"""End-to-end integration test for the MCP gateway.

Reuses the eval runner's helpers to:
  1. Upload the test docs for the chosen workflow
  2. Create the workflow via /workflows-cell-based
  3. Execute it once via /execute-stream (this generates cell code)
  4. Deploy the workflow as an MCP server via /api/workflow/deploy-mcp/{id}
  5. Call GET /mcp/{id}/tools with the bearer token
  6. Call POST /mcp/{id}/tools/call with the same file_ids and assert that
     the output contains the fields the eval manifest declares for the test.

Usage:
    python tests/eval/test_mcp_integration.py --base-url http://127.0.0.1:8000/api
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from typing import Any, Dict, List

import httpx

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from tests.eval.runner import (
    extract_workflow_description,
    extract_document_paths,
    extract_output_example,
    upload_documents,
    create_workflow,
    execute_workflow,
    get_workflow_plan,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("mcp-int")


def find_field_in_cells(plan: Dict[str, Any], field_name: str) -> Any:
    """Search a plan's cell outputs for a named field. Returns the value or None."""
    for cell in plan.get("cells", []):
        outputs = cell.get("output") or {}
        if isinstance(outputs, dict) and field_name in outputs:
            return outputs[field_name]
    return None


def find_field_in_mcp_text(text: str, field_name: str) -> bool:
    """Best-effort substring check for a field name in the MCP tool's text payload."""
    return field_name in text


async def run(base_url: str, test_name: str, workflow_file: str,
              expected_fields: List[str]) -> bool:
    """Run the full pipeline and return True on success."""
    api_base = base_url
    mcp_origin = base_url.rstrip("/").removesuffix("/api")

    description = extract_workflow_description(workflow_file)
    output_example = extract_output_example(workflow_file)
    doc_paths = extract_document_paths(workflow_file)
    logger.info("Test: %s", test_name)
    logger.info("  description: %d chars", len(description))
    logger.info("  documents: %s", doc_paths)

    async with httpx.AsyncClient() as client:
        # ---- Step 1: upload docs ----
        file_ids = await upload_documents(client, api_base, doc_paths, "tests/ugap-test")
        logger.info("  uploaded file_ids=%s", file_ids)

        # ---- Step 2: create workflow ----
        workflow_id = await create_workflow(
            client, api_base, description, file_ids, output_example=output_example
        )
        logger.info("  workflow_id=%s", workflow_id)

        # ---- Step 3: execute once to generate cell code ----
        logger.info("  executing workflow (this can take several minutes)...")
        t0 = time.time()
        await execute_workflow(client, api_base, workflow_id, file_ids)
        logger.info("  initial execution done in %.0fs", time.time() - t0)

        # Verify cells completed and grab their outputs for comparison.
        plan = await get_workflow_plan(client, api_base, workflow_id)
        cell_statuses = [(c.get("name"), c.get("status")) for c in plan.get("cells", [])]
        logger.info("  cell statuses: %s", cell_statuses)
        if not all(s == "completed" for _, s in cell_statuses):
            logger.error("  ABORT: not all cells completed via the original execution path")
            return False

        baseline_values = {f: find_field_in_cells(plan, f) for f in expected_fields}
        logger.info("  baseline outputs: %s", {
            k: (str(v)[:80] + "…") if v and len(str(v)) > 80 else v
            for k, v in baseline_values.items()
        })

        # ---- Step 4: deploy as MCP ----
        r = await client.post(f"{api_base}/workflow/deploy-mcp/{workflow_id}", timeout=30.0)
        if r.status_code != 200:
            logger.error("  deploy failed: %d %s", r.status_code, r.text)
            return False
        deploy_data = r.json()
        token = deploy_data["bearer_token"]
        tool_name = deploy_data["tool_name"]
        mcp_url = deploy_data["url"]
        logger.info("  deployed: url=%s tool=%s token=%s…%s",
                    mcp_url, tool_name, token[:4], token[-4:])

        # ---- Step 5: list tools (auth gate sanity check) ----
        bearer = {"Authorization": f"Bearer {token}"}
        r = await client.get(f"{mcp_origin}/mcp/{workflow_id}/tools", headers=bearer, timeout=30.0)
        if r.status_code != 200:
            logger.error("  /tools failed: %d %s", r.status_code, r.text)
            return False
        tools = r.json().get("tools", [])
        if not tools or tools[0]["name"] != tool_name:
            logger.error("  /tools returned unexpected payload: %s", r.json())
            return False
        logger.info("  /tools OK: %s", [t["name"] for t in tools])

        # Negative auth check: a wrong token must be rejected.
        r = await client.get(
            f"{mcp_origin}/mcp/{workflow_id}/tools",
            headers={"Authorization": "Bearer wrong-token"},
            timeout=10.0,
        )
        if r.status_code != 401:
            logger.error("  expected 401 for wrong token, got %d", r.status_code)
            return False
        logger.info("  /tools rejects wrong token (401) OK")

        # ---- Step 6: call the tool with file_ids ----
        body = {
            "name": tool_name,
            "arguments": {"query": "Execute workflow via MCP", "file_ids": file_ids},
        }
        logger.info("  calling /tools/call (this re-runs the workflow via MCP path)...")
        t0 = time.time()
        r = await client.post(
            f"{mcp_origin}/mcp/{workflow_id}/tools/call",
            headers=bearer,
            json=body,
            timeout=900.0,
        )
        elapsed = time.time() - t0
        if r.status_code != 200:
            logger.error("  /tools/call HTTP %d: %s", r.status_code, r.text)
            return False
        logger.info("  /tools/call done in %.0fs", elapsed)

        payload = r.json()
        content = payload.get("content") or []
        if not content or content[0].get("type") != "text":
            logger.error("  unexpected MCP response shape: %s", payload)
            return False

        text = content[0]["text"]
        # The tool's text is a JSON-serialised dict; try to parse for richer checks.
        try:
            parsed = json.loads(text)
            logger.info("  MCP result keys: %s", sorted(parsed.keys())[:20])
        except Exception:
            parsed = None
            logger.info("  MCP result (raw, first 400 chars): %s", text[:400])

        # ---- Step 7: assert expected fields ----
        all_ok = True
        for field in expected_fields:
            value = None
            if isinstance(parsed, dict):
                value = parsed.get(field)
            present = value not in (None, "", [], {})
            substr_ok = find_field_in_mcp_text(text, field)
            ok = present or substr_ok
            preview = (str(value)[:80] + "…") if value and len(str(value)) > 80 else value
            logger.info("  field %-20s present=%s value=%r", field, ok, preview)
            if not ok:
                all_ok = False

        if not all_ok:
            logger.error("  FAIL: one or more expected fields missing from MCP output")
            return False

        # Sanity: error response from the tool path would have status=failed.
        if isinstance(parsed, dict) and parsed.get("status") == "failed":
            logger.error("  FAIL: MCP tool returned an error response: %s", parsed.get("error"))
            return False

        logger.info("  PASS: %s", test_name)
        return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api")
    parser.add_argument(
        "--workflow-file",
        default="tests/ugap-test/test-single-doc-extraction.md",
        help="Path to a test workflow markdown file (relative to project root)",
    )
    parser.add_argument(
        "--expect-field",
        action="append",
        default=None,
        help="Field name expected in the workflow result. May be repeated. "
             "Defaults to holder_siret + holder_name for the single-doc test.",
    )
    parser.add_argument("--name", default="single-doc-extraction-mcp")
    args = parser.parse_args()

    expected = args.expect_field or ["holder_siret", "holder_name", "holder_address", "holder_legal_form"]

    ok = asyncio.run(run(args.base_url, args.name, args.workflow_file, expected))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
