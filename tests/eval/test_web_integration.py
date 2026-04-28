#!/usr/bin/env python3
"""End-to-end integration test for the Web App gateway.

For each workflow under test, this script:
  1. Uploads the workflow's documents to Paradigm.
  2. Creates the workflow plan and seeds it via /execute-stream so cells get
     their generated_code populated.
  3. Deploys the workflow as a web app via /api/workflow/deploy-web/{id}.
  4. Fetches /app/{id}/ (HTML) and /app/{id}/config.json with token + cookie.
  5. POSTs /app/{id}/execute with multipart user_input + ALL the workflow's
     documents, and asserts the extracted final_result contains expected
     substrings.
  6. Downloads the workflow package and asserts the ZIP's frontend/config.json
     matches the live config.json byte-for-byte (the parity contract).

Two run modes:
    --workflow-file FILE         single workflow (manual debugging)
    --from-manifest-tags TAG[,…] bulk: every manifest entry whose tags match

Free flakiness signal:
After seeding, this reads each cell's ``evaluation_attempts`` from the plan.
Cells that needed >1 attempt got past the executor's retry loop on the
second/third try — a quiet hint that the planner/generator produced fragile
code. Reported as a per-workflow warning; does NOT fail the run by itself.
"""

import argparse
import asyncio
import io
import json
import logging
import os
import sys
import time
import zipfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import httpx

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from tests.eval.runner import (
    create_workflow,
    execute_workflow,
    extract_document_paths,
    extract_output_example,
    extract_workflow_description,
    get_workflow_plan,
    load_manifest,
    upload_documents,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("web-int")

# Per-workflow expected substrings. Best-effort: a workflow not listed here
# falls back to a generic "result is non-empty and not an error message" check.
# Add entries when you pin down what a workflow MUST produce on a known input.
DEFAULT_EXPECTED: Dict[str, List[str]] = {
    "test-single-doc-extraction.md": ["513 082 503", "INOP"],
    "test-cross-doc-comparison.md": ["INOP"],          # same INOP'S in both files
    "e2e-test-workflow.md": ["INOP"],                  # multi-doc DC4 + Acte
}


@dataclass
class WorkflowResult:
    """Outcome of one workflow run through the web-app pipeline."""
    workflow: str
    passed: bool
    reason: str = ""             # one-line failure summary; empty on pass
    elapsed: float = 0.0
    flaky_cells: List[Tuple[str, int]] = field(default_factory=list)


def _generic_substrings_for(workflow_file: str) -> List[str]:
    """Look up expected substrings in the table; return [] if no entry."""
    name = os.path.basename(workflow_file)
    return DEFAULT_EXPECTED.get(name, [])


def _flaky_cells_from_plan(plan: Dict[str, Any]) -> List[Tuple[str, int]]:
    """Return [(cell_name, attempts)] for any cell that needed >1 attempt.

    The executor retries cells silently when their LLM judge fails or when
    execution raises. ``evaluation_attempts`` records the count. Cells that
    needed >1 attempt to pass are a non-fatal flakiness signal — the workflow
    succeeded, but only after the executor papered over a brittle cell.
    """
    flaky: List[Tuple[str, int]] = []
    for c in plan.get("cells", []):
        attempts = c.get("evaluation_attempts") or 0
        if attempts and attempts > 1:
            flaky.append((c.get("name", "?"), attempts))
    return flaky


async def run_one(
    base_url: str,
    workflow_file: str,
    expected_substrings: Optional[List[str]] = None,
) -> WorkflowResult:
    """Run the full pipeline for one workflow file. Returns a WorkflowResult."""
    api_base = base_url
    origin = base_url.rstrip("/").removesuffix("/api")

    if expected_substrings is None:
        expected_substrings = _generic_substrings_for(workflow_file)

    description = extract_workflow_description(workflow_file)
    output_example = extract_output_example(workflow_file)
    doc_paths = extract_document_paths(workflow_file)
    logger.info("=== %s (%d docs) ===", os.path.basename(workflow_file), len(doc_paths))
    logger.info("  documents: %s", doc_paths)

    started = time.time()
    result = WorkflowResult(workflow=workflow_file, passed=False)

    try:
        async with httpx.AsyncClient() as client:
            # --- Seed: upload, plan, execute once ---
            file_ids = await upload_documents(client, api_base, doc_paths, "tests/ugap-test")
            workflow_id = await create_workflow(
                client, api_base, description, file_ids, output_example=output_example
            )
            logger.info("  workflow_id=%s, seeding via /execute-stream...", workflow_id)
            await execute_workflow(client, api_base, workflow_id, file_ids)

            plan = await get_workflow_plan(client, api_base, workflow_id)
            cell_statuses = [(c.get("name"), c.get("status")) for c in plan.get("cells", [])]
            if not all(s == "completed" for _, s in cell_statuses):
                failed = [n for n, s in cell_statuses if s != "completed"]
                result.reason = "seeding /execute-stream failed (cells: {})".format(failed)
                return result

            # Free flakiness signal — read it whether the run passes or fails.
            result.flaky_cells = _flaky_cells_from_plan(plan)

            # --- Deploy ---
            r = await client.post(f"{api_base}/workflow/deploy-web/{workflow_id}", timeout=120.0)
            if r.status_code != 200:
                result.reason = "deploy-web {} {}".format(r.status_code, r.text[:120])
                return result
            deploy = r.json()
            token = deploy["access_token"]
            workflow_id = deploy["workflow_id"]
            logger.info("  deployed: ui=%s", deploy.get("ui_config_summary"))

            # --- Fetch HTML + config.json ---
            r = await client.get(
                f"{origin}/app/{workflow_id}/",
                params={"token": token},
                timeout=30.0,
            )
            if r.status_code != 200:
                result.reason = "GET /app/.../ {}".format(r.status_code)
                return result
            html = r.text
            if deploy["workflow_name"] not in html:
                result.reason = "served HTML missing workflow name"
                return result
            if f"/app/{workflow_id}" not in html:
                result.reason = "API_BASE substitution missing in HTML"
                return result

            r = await client.get(f"{origin}/app/{workflow_id}/config.json", timeout=30.0)
            if r.status_code != 200:
                result.reason = "GET /config.json {}".format(r.status_code)
                return result
            live_config = r.json()
            if not isinstance(live_config, dict) or "files" not in live_config:
                result.reason = "live config malformed: {}".format(list(live_config.keys()) if isinstance(live_config, dict) else type(live_config))
                return result

            # --- POST /execute with ALL the workflow's docs ---
            files_form = []
            for doc in doc_paths:
                p = os.path.join(PROJECT_ROOT, "tests", "ugap-test", doc)
                with open(p, "rb") as f:
                    files_form.append(("files", (os.path.basename(p), f.read(), "application/pdf")))
            data_form = {"user_input": "Run via web app"}

            logger.info("  calling /execute with %d file(s)...", len(files_form))
            t_exec = time.time()
            r = await client.post(
                f"{origin}/app/{workflow_id}/execute",
                files=files_form,
                data=data_form,
                timeout=900.0,
            )
            exec_elapsed = time.time() - t_exec
            if r.status_code != 200:
                result.reason = "POST /execute {}: {}".format(r.status_code, r.text[:160])
                return result
            body = r.json()
            logger.info("  /execute done in %.0fs status=%s", exec_elapsed, body.get("status"))
            if body.get("status") != "completed":
                result.reason = "web-app /execute returned status={}: {}".format(
                    body.get("status"), str(body.get("result"))[:160]
                )
                return result

            result_text = body.get("result", "")
            if not isinstance(result_text, str) or not result_text:
                result.reason = "web-app /execute result empty"
                return result

            # Generic sanity: not an error string disguised as success.
            if "Workflow execution failed" in result_text:
                result.reason = "result text starts with 'Workflow execution failed' (cell-level error surfaced as result)"
                return result

            # Specific substrings if we have them for this workflow.
            missing = [s for s in expected_substrings if s not in result_text]
            if missing:
                result.reason = "expected substrings missing: {}".format(missing)
                logger.info("  result preview: %s", result_text[:300])
                return result

            # --- Download ZIP, assert config.json parity ---
            r = await client.post(f"{api_base}/workflow/generate-package/{workflow_id}", timeout=120.0)
            if r.status_code != 200:
                result.reason = "generate-package {}".format(r.status_code)
                return result
            with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
                if "frontend/config.json" not in zf.namelist():
                    result.reason = "ZIP missing frontend/config.json"
                    return result
                zip_config = json.loads(zf.read("frontend/config.json").decode("utf-8"))
            if zip_config != live_config:
                result.reason = "ZIP/live config.json parity broken"
                return result

            result.passed = True
            return result

    except Exception as e:
        logger.exception("unexpected exception during %s", workflow_file)
        result.reason = "exception: {}".format(e)
        return result
    finally:
        result.elapsed = round(time.time() - started, 1)


# ---------------------------------------------------------------------------
# CLI / orchestration
# ---------------------------------------------------------------------------


def _workflows_from_manifest_tags(tags: List[str]) -> List[str]:
    """Return manifest workflow files whose tags include ALL given tags."""
    manifest = load_manifest()
    matched: List[str] = []
    for entry in manifest.get("tests", []):
        entry_tags = entry.get("tags", []) or []
        if all(tag in entry_tags for tag in tags):
            matched.append(entry["workflow_file"])
    return matched


def _print_summary(results: List[WorkflowResult]) -> None:
    """Print a compact final report. Flakiness shown but does not affect status."""
    pad = max((len(os.path.basename(r.workflow)) for r in results), default=0)
    print()
    print("=== Web-app integration summary ===")
    for r in results:
        name = os.path.basename(r.workflow).ljust(pad)
        status = "PASS" if r.passed else "FAIL"
        line = "  [{}] {}  ({:.0f}s)".format(status, name, r.elapsed)
        if not r.passed:
            line += "  — {}".format(r.reason)
        print(line)
        if r.flaky_cells:
            details = ", ".join("{}={}".format(n, a) for n, a in r.flaky_cells)
            print("        ⚠ flakiness: cells needed retries → {}".format(details))
    passed = sum(1 for r in results if r.passed)
    print("  total: {}/{} passed".format(passed, len(results)))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api")
    parser.add_argument(
        "--workflow-file",
        default=None,
        help="Path to a single workflow markdown file (relative to project root).",
    )
    parser.add_argument(
        "--from-manifest-tags",
        default=None,
        help="Comma-separated tag list. Runs every manifest entry whose tags include ALL listed tags. "
             "Mutually exclusive with --workflow-file.",
    )
    parser.add_argument(
        "--expect-substring",
        action="append",
        default=None,
        help="Expected substring in the workflow's final result. Repeatable. "
             "Only meaningful with --workflow-file. Defaults from a built-in table per workflow.",
    )
    args = parser.parse_args()

    if args.from_manifest_tags and args.workflow_file:
        parser.error("--workflow-file and --from-manifest-tags are mutually exclusive")

    if args.from_manifest_tags:
        tags = [t.strip() for t in args.from_manifest_tags.split(",") if t.strip()]
        workflows = _workflows_from_manifest_tags(tags)
        if not workflows:
            print("No manifest entries match tags: {}".format(tags))
            return 1
        logger.info("Running %d workflow(s) matching tags %s", len(workflows), tags)
    else:
        workflows = [args.workflow_file or "tests/ugap-test/test-single-doc-extraction.md"]

    async def runner():
        results = []
        for wf in workflows:
            expected = args.expect_substring if (args.expect_substring and args.workflow_file) else None
            results.append(await run_one(args.base_url, wf, expected))
        return results

    results = asyncio.run(runner())
    _print_summary(results)
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
