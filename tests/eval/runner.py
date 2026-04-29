#!/usr/bin/env python3
"""Eval suite runner for the workflow builder.

Automates the manual test process: upload docs → create workflow → execute → check results.
Runs against a live backend and produces JSON reports with per-workflow metrics.

Usage:
    python tests/eval/runner.py                          # Run all tests
    python tests/eval/runner.py --filter single-doc      # Run matching tests
    python tests/eval/runner.py --tags extraction,en     # Run tests with ALL listed tags
    python tests/eval/runner.py --compare a.json b.json  # Compare two reports
"""

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
from typing import Dict, Any, List, Optional

import httpx
import yaml
from dotenv import load_dotenv

# Add project root to path for imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

# Load .env from repo root so API keys are available to llm_judge and any
# downstream calls. Done at import so --compare also picks them up if needed.
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from tests.eval.assertions import run_assertions
from tests.eval.reporter import generate_report, save_report, compare_reports, print_comparison

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Default backend URL
DEFAULT_BASE_URL = "http://localhost:8000/api"

# Directories
EVAL_DIR = os.path.dirname(os.path.abspath(__file__))
REPORTS_DIR = os.path.join(EVAL_DIR, "reports")
MANIFEST_PATH = os.path.join(EVAL_DIR, "manifest.yaml")


def load_manifest(manifest_path: str = None) -> Dict[str, Any]:
    """Load the eval manifest YAML file."""
    path = manifest_path or MANIFEST_PATH
    with open(path, "r") as f:
        return yaml.safe_load(f)


def extract_workflow_description(workflow_file: str) -> str:
    """Extract the workflow description from a test markdown file.

    Looks for the content between ``` markers under the
    '## Workflow description' section.
    """
    full_path = os.path.join(PROJECT_ROOT, workflow_file)
    with open(full_path, "r") as f:
        content = f.read()

    # Find the code block in the workflow description section
    # Handles both English "Workflow description" and French "Description du workflow"
    match = re.search(
        r'##\s*(?:Workflow description|Description du workflow).*?```\n(.*?)```',
        content,
        re.DOTALL | re.IGNORECASE
    )
    if match:
        return match.group(1).strip()

    # Fallback: find the first ``` code block after a ## heading containing "description" or "workflow"
    match = re.search(
        r'##\s*[^\n]*(?:description|workflow)[^\n]*\n.*?```\n(.*?)```',
        content,
        re.DOTALL | re.IGNORECASE
    )
    if match:
        return match.group(1).strip()

    raise ValueError("Could not extract workflow description from {}".format(workflow_file))


def extract_document_paths(workflow_file: str) -> List[str]:
    """Extract document paths from a test markdown file.

    Looks for backtick-quoted paths in the '## Input documents' section.
    """
    full_path = os.path.join(PROJECT_ROOT, workflow_file)
    with open(full_path, "r") as f:
        content = f.read()

    # Find the input documents section (EN or FR)
    match = re.search(
        r'##\s*(?:Input documents|Documents d\'entr[eé]e).*?\n(.*?)(?=\n##|\Z)',
        content,
        re.DOTALL | re.IGNORECASE
    )
    if not match:
        return []

    section = match.group(1)
    # Extract paths in backticks
    paths = re.findall(r'`([^`]+\.pdf)`', section, re.IGNORECASE)
    return paths


def extract_output_example(workflow_file: str) -> Optional[str]:
    """Extract the output example from a test markdown file.

    Looks for the content between ``` markers under the
    '## Output example' section. Returns None if not found.
    """
    full_path = os.path.join(PROJECT_ROOT, workflow_file)
    with open(full_path, "r") as f:
        content = f.read()

    match = re.search(
        r'##\s*(?:Output example|Exemple de sortie).*?```\n(.*?)```',
        content,
        re.DOTALL | re.IGNORECASE
    )
    if match:
        return match.group(1).strip()
    return None


async def upload_documents(
    client: httpx.AsyncClient,
    base_url: str,
    doc_paths: List[str],
    test_dir: str
) -> List[int]:
    """Upload documents and return their file IDs."""
    file_ids = []
    for doc_path in doc_paths:
        # Resolve relative path from test directory
        full_path = os.path.join(PROJECT_ROOT, test_dir, doc_path)
        if not os.path.exists(full_path):
            # Try from ugap-test directory
            full_path = os.path.join(PROJECT_ROOT, "tests", "ugap-test", doc_path)
        if not os.path.exists(full_path):
            raise FileNotFoundError("Document not found: {} (tried {})".format(doc_path, full_path))

        filename = os.path.basename(full_path)
        with open(full_path, "rb") as f:
            files = {"file": (filename, f, "application/pdf")}
            response = await client.post(
                "{}/files/upload".format(base_url),
                files=files,
                timeout=60.0
            )
            response.raise_for_status()
            data = response.json()
            file_id = data["id"]
            file_ids.append(file_id)
            logger.info("  Uploaded {} -> file_id={}".format(filename, file_id))

    return file_ids


async def create_workflow(
    client: httpx.AsyncClient,
    base_url: str,
    description: str,
    file_ids: List[int],
    output_example: Optional[str] = None
) -> str:
    """Create a workflow and return its ID."""
    payload = {
        "description": description,
        "context": {"attached_file_ids": file_ids}
    }
    if output_example:
        payload["output_example"] = output_example
    response = await client.post(
        "{}/workflows-cell-based".format(base_url),
        json=payload,
        timeout=120.0
    )
    response.raise_for_status()
    data = response.json()
    workflow_id = data.get("workflow_id") or data.get("id")
    logger.info("  Created workflow: {}".format(workflow_id))
    return workflow_id


async def execute_workflow(
    client: httpx.AsyncClient,
    base_url: str,
    workflow_id: str,
    file_ids: List[int]
) -> None:
    """Execute a workflow via SSE stream, consuming all events."""
    payload = {
        "user_input": "Execute workflow",
        "attached_file_ids": file_ids,
        "stream": True
    }

    # Use a long timeout for workflow execution
    async with client.stream(
        "POST",
        "{}/workflows/{}/execute-stream".format(base_url, workflow_id),
        json=payload,
        timeout=600.0
    ) as response:
        response.raise_for_status()
        event_count = 0
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                event_count += 1
                try:
                    event = json.loads(line[6:])
                    event_type = event.get("type", "")
                    if event_type == "cell_completed":
                        logger.info("    Cell completed: {} ({:.1f}s)".format(
                            event.get("cell_name", "?"),
                            event.get("execution_time", 0)))
                    elif event_type == "cell_failed":
                        logger.warning("    Cell failed: {} - {}".format(
                            event.get("cell_name", "?"),
                            event.get("error", "?")[:100]))
                    elif event_type == "workflow_completed":
                        logger.info("    Workflow completed")
                    elif event_type == "workflow_failed":
                        logger.warning("    Workflow failed: {}".format(
                            event.get("error", "?")[:100]))
                except json.JSONDecodeError:
                    pass

        logger.info("  Consumed {} SSE events".format(event_count))


async def get_workflow_plan(
    client: httpx.AsyncClient,
    base_url: str,
    workflow_id: str
) -> Dict[str, Any]:
    """Fetch the workflow plan with results."""
    response = await client.get(
        "{}/workflows/{}/plan".format(base_url, workflow_id),
        timeout=30.0
    )
    response.raise_for_status()
    return response.json()


async def run_single_test(
    client: httpx.AsyncClient,
    base_url: str,
    test_config: Dict[str, Any]
) -> Dict[str, Any]:
    """Run a single eval test and return results."""
    name = test_config["name"]
    workflow_file = test_config["workflow_file"]
    doc_overrides = test_config.get("documents", [])
    assertions_config = test_config.get("assertions", [])
    tags = test_config.get("tags", [])

    logger.info("Running test: {}".format(name))
    start_time = time.time()

    result = {
        "name": name,
        "workflow_file": workflow_file,
        "tags": tags,
        "status": "error",
        "time_seconds": 0,
        "cells": [],
        "assertions": [],
        "error": None,
    }

    try:
        # Step 1: Extract workflow description and optional output example
        description = extract_workflow_description(workflow_file)
        logger.info("  Extracted workflow description ({} chars)".format(len(description)))

        # Extract output_example from file or manifest override
        output_example = test_config.get("output_example") or extract_output_example(workflow_file)
        if output_example:
            logger.info("  Found output_example ({} chars)".format(len(output_example)))

        # Step 2: Determine document paths
        if doc_overrides:
            doc_paths = doc_overrides
        else:
            doc_paths = extract_document_paths(workflow_file)
        logger.info("  Documents: {}".format(doc_paths))

        # Step 3: Upload documents
        file_ids = await upload_documents(client, base_url, doc_paths, "tests/ugap-test")
        logger.info("  File IDs: {}".format(file_ids))

        # Step 4: Create workflow
        workflow_id = await create_workflow(client, base_url, description, file_ids,
                                            output_example=output_example)

        # Step 5: Execute workflow
        await execute_workflow(client, base_url, workflow_id, file_ids)

        # Step 6: Fetch results
        plan = await get_workflow_plan(client, base_url, workflow_id)

        elapsed = time.time() - start_time
        result["time_seconds"] = round(elapsed, 1)
        result["workflow_id"] = workflow_id

        # Extract cell summaries
        for cell in plan.get("cells", []):
            result["cells"].append({
                "name": cell.get("name", "?"),
                "display_step": cell.get("display_step", "?"),
                "status": cell.get("status", "?"),
                "time": cell.get("execution_time"),
                "evaluation_score": cell.get("evaluation_score"),
                "evaluation_attempts": cell.get("evaluation_attempts", 0),
            })

        # Step 7: Run assertions
        assertion_results = run_assertions(plan, assertions_config, total_time=elapsed)
        result["assertions"] = [ar.to_dict() for ar in assertion_results]

        # Determine overall status
        all_passed = all(ar.passed for ar in assertion_results)
        result["status"] = "passed" if all_passed else "failed"
        if not all_passed:
            failed_assertions = [ar for ar in assertion_results if not ar.passed]
            result["error"] = "; ".join(
                "{}: {}".format(ar.assertion_type, ar.detail) for ar in failed_assertions)

    except Exception as e:
        elapsed = time.time() - start_time
        result["time_seconds"] = round(elapsed, 1)
        result["status"] = "error"
        result["error"] = str(e)
        logger.error("  Test error: {}".format(str(e)))

    status_icon = {"passed": "PASS", "failed": "FAIL", "error": "ERROR"}.get(result["status"], "?")
    logger.info("[{}] {} ({:.0f}s)".format(status_icon, name, result["time_seconds"]))
    return result


async def run_all_tests(
    manifest: Dict[str, Any],
    base_url: str,
    filter_name: Optional[str] = None,
    filter_tags: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Run all tests from the manifest, optionally filtered."""
    tests = manifest.get("tests", [])

    if filter_name:
        tests = [t for t in tests if filter_name.lower() in t["name"].lower()]

    if filter_tags:
        # Tests must have ALL listed tags
        tests = [t for t in tests
                 if all(tag in t.get("tags", []) for tag in filter_tags)]

    if not tests:
        logger.warning("No tests matched the filter criteria")
        return []

    logger.info("Running {} tests against {}".format(len(tests), base_url))

    results = []
    async with httpx.AsyncClient() as client:
        for test_config in tests:
            result = await run_single_test(client, base_url, test_config)
            results.append(result)

    return results


def print_summary(report: Dict[str, Any]):
    """Print a human-readable summary of the eval run."""
    summary = report["summary"]
    print("\n=== Eval Summary ===")
    print("Total: {}  Passed: {}  Failed: {}  Errored: {}  Time: {:.0f}s  Pass rate: {:.0%}".format(
        summary["total"], summary["passed"], summary["failed"],
        summary["errored"], summary["total_time_seconds"], summary["pass_rate"]))

    for test in report["tests"]:
        status = test["status"].upper()
        icon = {"PASSED": "PASS", "FAILED": "FAIL", "ERROR": "ERROR"}.get(status, "?")
        line = "  [{}] {} ({:.0f}s)".format(icon, test["name"], test["time_seconds"])
        if test.get("error"):
            line += " - {}".format(test["error"][:120])
        print(line)

        # Show assertion details for failures
        if test["status"] != "passed":
            for assertion in test.get("assertions", []):
                if not assertion["passed"]:
                    print("         {} : {}".format(assertion["type"], assertion["detail"][:100]))
    print()


def main():
    parser = argparse.ArgumentParser(description="Workflow builder eval suite runner")
    parser.add_argument("--manifest", default=MANIFEST_PATH, help="Path to eval manifest YAML")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Backend API base URL")
    parser.add_argument("--filter", dest="filter_name", help="Filter tests by name substring")
    parser.add_argument("--tags", help="Filter tests by tags (comma-separated, requires ALL)")
    parser.add_argument("--compare", nargs=2, metavar=("REPORT_A", "REPORT_B"),
                        help="Compare two report files")
    parser.add_argument("--no-save", action="store_true", help="Don't save report to disk")

    args = parser.parse_args()

    # Compare mode
    if args.compare:
        with open(args.compare[0]) as f:
            report_a = json.load(f)
        with open(args.compare[1]) as f:
            report_b = json.load(f)
        comparison = compare_reports(report_a, report_b)
        print_comparison(comparison)
        return

    # Run mode — verify required API keys are present before any test runs.
    # Without these, llm_judge assertions silently "fail" with key-missing errors,
    # which is indistinguishable from a real judgment regression.
    missing = [k for k in ("LIGHTON_API_KEY", "ANTHROPIC_API_KEY") if not os.environ.get(k)]
    if missing:
        sys.exit(
            "ERROR: required env vars not set: {}. "
            "Add them to .env at the repo root or export them before running.".format(", ".join(missing))
        )

    manifest = load_manifest(args.manifest)
    filter_tags = args.tags.split(",") if args.tags else None

    results = asyncio.run(run_all_tests(
        manifest=manifest,
        base_url=args.base_url,
        filter_name=args.filter_name,
        filter_tags=filter_tags,
    ))

    report = generate_report(results)
    print_summary(report)

    if not args.no_save:
        filepath = save_report(report, REPORTS_DIR)
        print("Report saved to: {}".format(filepath))


if __name__ == "__main__":
    main()
