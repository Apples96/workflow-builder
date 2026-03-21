"""JSON report generation for eval runs.

Produces per-run reports with per-workflow and per-cell metrics,
stored in tests/eval/reports/ for regression tracking.
"""

import json
import os
from datetime import datetime
from typing import Dict, Any, List


def generate_report(test_results: List[Dict[str, Any]], run_id: str = None) -> Dict[str, Any]:
    """Generate a structured report from test results.

    Args:
        test_results: List of per-test result dicts from the runner.
        run_id: Optional run ID. Defaults to current timestamp.

    Returns:
        Report dict with summary and per-test details.
    """
    if not run_id:
        run_id = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

    total = len(test_results)
    passed = sum(1 for t in test_results if t.get("status") == "passed")
    failed = sum(1 for t in test_results if t.get("status") == "failed")
    errored = sum(1 for t in test_results if t.get("status") == "error")
    skipped = total - passed - failed - errored
    total_time = sum(t.get("time_seconds", 0) for t in test_results)

    report = {
        "run_id": run_id,
        "timestamp": datetime.utcnow().isoformat(),
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "errored": errored,
            "skipped": skipped,
            "total_time_seconds": round(total_time, 1),
            "pass_rate": round(passed / total, 2) if total > 0 else 0.0
        },
        "tests": test_results
    }

    return report


def save_report(report: Dict[str, Any], reports_dir: str) -> str:
    """Save a report to the reports directory.

    Args:
        report: Report dict to save.
        reports_dir: Directory to save reports in.

    Returns:
        Path to the saved report file.
    """
    os.makedirs(reports_dir, exist_ok=True)

    # Use run_id as filename, sanitized
    run_id = report.get("run_id", "unknown")
    safe_name = run_id.replace(":", "-").replace(" ", "_")
    filename = "eval-{}.json".format(safe_name)
    filepath = os.path.join(reports_dir, filename)

    with open(filepath, "w") as f:
        json.dump(report, f, indent=2, default=str)

    return filepath


def compare_reports(report_a: Dict, report_b: Dict) -> Dict[str, Any]:
    """Compare two eval reports for regression detection.

    Args:
        report_a: Baseline report (older).
        report_b: New report (newer).

    Returns:
        Comparison dict with regressions and improvements.
    """
    comparison = {
        "baseline_run_id": report_a.get("run_id"),
        "new_run_id": report_b.get("run_id"),
        "summary": {
            "baseline_pass_rate": report_a.get("summary", {}).get("pass_rate", 0),
            "new_pass_rate": report_b.get("summary", {}).get("pass_rate", 0),
        },
        "regressions": [],
        "improvements": [],
        "unchanged": [],
    }

    # Build lookup by test name
    tests_a = {t["name"]: t for t in report_a.get("tests", []) if "name" in t}
    tests_b = {t["name"]: t for t in report_b.get("tests", []) if "name" in t}

    all_names = sorted(set(list(tests_a.keys()) + list(tests_b.keys())))

    for name in all_names:
        ta = tests_a.get(name)
        tb = tests_b.get(name)

        if not ta or not tb:
            continue

        status_a = ta.get("status", "unknown")
        status_b = tb.get("status", "unknown")

        if status_a == "passed" and status_b != "passed":
            comparison["regressions"].append({
                "test": name,
                "was": status_a,
                "now": status_b,
                "error": tb.get("error", "")
            })
        elif status_a != "passed" and status_b == "passed":
            comparison["improvements"].append({
                "test": name,
                "was": status_a,
                "now": status_b
            })
        else:
            comparison["unchanged"].append(name)

    return comparison


def print_comparison(comparison: Dict[str, Any]):
    """Print a human-readable comparison summary."""
    baseline_rate = comparison["summary"]["baseline_pass_rate"]
    new_rate = comparison["summary"]["new_pass_rate"]

    print("\n=== Eval Comparison ===")
    print("Baseline: {} (pass rate: {:.0%})".format(
        comparison["baseline_run_id"], baseline_rate))
    print("New:      {} (pass rate: {:.0%})".format(
        comparison["new_run_id"], new_rate))

    if comparison["regressions"]:
        print("\nREGRESSIONS ({})".format(len(comparison["regressions"])))
        for r in comparison["regressions"]:
            print("  {} : {} -> {} {}".format(
                r["test"], r["was"], r["now"],
                "({})".format(r["error"][:80]) if r.get("error") else ""))

    if comparison["improvements"]:
        print("\nIMPROVEMENTS ({})".format(len(comparison["improvements"])))
        for i in comparison["improvements"]:
            print("  {} : {} -> {}".format(i["test"], i["was"], i["now"]))

    if not comparison["regressions"] and not comparison["improvements"]:
        print("\nNo changes detected.")

    print()
