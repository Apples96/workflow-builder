#!/usr/bin/env python3
"""
Test script for cell-based workflow architecture.

This script tests the new cell-based workflow endpoints:
1. POST /api/workflows-cell-based - Create a cell-based workflow
2. GET /api/workflows/{id}/plan - Get the workflow plan
3. POST /api/workflows/{id}/execute-stream - Execute with streaming

Run with: python test_cell_based.py
"""

import asyncio
import aiohttp
import json
import sys

# Configuration
BASE_URL = "http://localhost:8000"
API_BASE = "{}/api".format(BASE_URL)


async def test_create_cell_based_workflow():
    """Test creating a cell-based workflow."""
    print("\n" + "=" * 60)
    print("TEST 1: Create Cell-Based Workflow")
    print("=" * 60)

    async with aiohttp.ClientSession() as session:
        payload = {
            "description": "Search for documents about artificial intelligence and summarize the key findings",
            "name": "AI Document Search"
        }

        print("\nRequest: POST /api/workflows-cell-based")
        print("Payload: {}".format(json.dumps(payload, indent=2)))

        try:
            async with session.post(
                "{}/workflows-cell-based".format(API_BASE),
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                print("\nStatus: {}".format(response.status))

                if response.status == 200:
                    data = await response.json()
                    print("\nResponse:")
                    print("  - Workflow ID: {}".format(data.get("id")))
                    print("  - Status: {}".format(data.get("status")))
                    print("  - Execution Mode: {}".format(data.get("execution_mode")))

                    plan = data.get("plan", {})
                    print("\n  Plan:")
                    print("    - Total Cells: {}".format(plan.get("total_cells")))

                    cells = plan.get("cells", [])
                    for cell in cells:
                        print("\n    Cell {}: {}".format(cell.get("step_number"), cell.get("name")))
                        print("      - Description: {}".format(cell.get("description")[:80]))
                        print("      - Inputs: {}".format(cell.get("inputs_required")))
                        print("      - Outputs: {}".format(cell.get("outputs_produced")))
                        print("      - Tools: {}".format(cell.get("paradigm_tools_used")))

                    return data.get("id")
                else:
                    error_text = await response.text()
                    print("\nError: {}".format(error_text))
                    return None

        except aiohttp.ClientError as e:
            print("\nConnection Error: {}".format(str(e)))
            print("Make sure the server is running on {}".format(BASE_URL))
            return None


async def test_get_workflow_plan(workflow_id: str):
    """Test retrieving a workflow plan."""
    print("\n" + "=" * 60)
    print("TEST 2: Get Workflow Plan")
    print("=" * 60)

    async with aiohttp.ClientSession() as session:
        print("\nRequest: GET /api/workflows/{}/plan".format(workflow_id))

        try:
            async with session.get(
                "{}/workflows/{}/plan".format(API_BASE, workflow_id),
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                print("\nStatus: {}".format(response.status))

                if response.status == 200:
                    data = await response.json()
                    print("\nPlan retrieved successfully")
                    print("  - Plan ID: {}".format(data.get("id")))
                    print("  - Total Cells: {}".format(data.get("total_cells")))
                    print("  - Status: {}".format(data.get("status")))
                    return True
                else:
                    error_text = await response.text()
                    print("\nError: {}".format(error_text))
                    return False

        except aiohttp.ClientError as e:
            print("\nConnection Error: {}".format(str(e)))
            return False


async def test_execute_stream(workflow_id: str):
    """Test streaming execution of a workflow."""
    print("\n" + "=" * 60)
    print("TEST 3: Execute Workflow with Streaming")
    print("=" * 60)

    async with aiohttp.ClientSession() as session:
        payload = {
            "user_input": "What are the latest developments in AI?",
            "stream": True
        }

        print("\nRequest: POST /api/workflows/{}/execute-stream".format(workflow_id))
        print("Payload: {}".format(json.dumps(payload, indent=2)))
        print("\nStreaming events:")
        print("-" * 40)

        try:
            async with session.post(
                "{}/workflows/{}/execute-stream".format(API_BASE, workflow_id),
                json=payload,
                timeout=aiohttp.ClientTimeout(total=300)  # 5 min timeout for execution
            ) as response:
                print("Status: {}".format(response.status))

                if response.status == 200:
                    # Read SSE stream
                    async for line in response.content:
                        line = line.decode('utf-8').strip()
                        if line.startswith('data:'):
                            event_data = line[5:].strip()
                            try:
                                event = json.loads(event_data)
                                event_type = event.get("type", "unknown")

                                if event_type == "workflow_start":
                                    print("\n[WORKFLOW START] Total cells: {}".format(
                                        event.get("total_cells")
                                    ))

                                elif event_type == "cell_generating":
                                    print("\n[CELL GENERATING] {} (Step {})".format(
                                        event.get("cell_name"),
                                        event.get("step_number")
                                    ))

                                elif event_type == "cell_ready":
                                    print("[CELL READY] Code generated for {}".format(
                                        event.get("cell_name")
                                    ))

                                elif event_type == "cell_executing":
                                    print("[CELL EXECUTING] Running {}...".format(
                                        event.get("cell_name")
                                    ))

                                elif event_type == "cell_completed":
                                    print("[CELL COMPLETED] {} ({:.2f}s)".format(
                                        event.get("cell_name"),
                                        event.get("execution_time", 0)
                                    ))
                                    output = event.get("output", "")
                                    if output:
                                        print("  Output: {}...".format(output[:100]))

                                elif event_type == "cell_failed":
                                    print("[CELL FAILED] {}: {}".format(
                                        event.get("cell_name"),
                                        event.get("error")
                                    ))

                                elif event_type == "workflow_completed":
                                    print("\n[WORKFLOW COMPLETED]")
                                    final_result = event.get("final_result", "")
                                    print("Final Result: {}...".format(final_result[:200]))
                                    return True

                                elif event_type == "workflow_failed":
                                    print("\n[WORKFLOW FAILED] {}".format(event.get("error")))
                                    return False

                                elif event_type == "error":
                                    print("\n[ERROR] {}".format(event.get("error")))
                                    return False

                            except json.JSONDecodeError:
                                print("Raw: {}".format(line))

                    return True
                else:
                    error_text = await response.text()
                    print("\nError: {}".format(error_text))
                    return False

        except asyncio.TimeoutError:
            print("\nTimeout: Execution took too long")
            return False
        except aiohttp.ClientError as e:
            print("\nConnection Error: {}".format(str(e)))
            return False


async def test_syntax_check():
    """Test that the modules can be imported without errors."""
    print("\n" + "=" * 60)
    print("TEST 0: Syntax Check (Import Modules)")
    print("=" * 60)

    try:
        # Try importing the new modules
        print("\nImporting cell_planner...")
        from api.workflow.cell.planner import WorkflowPlanner  # noqa: F401
        print("  OK")

        print("Importing cell_generator...")
        from api.workflow.cell.generator import CellCodeGenerator  # noqa: F401
        print("  OK")

        print("Importing cell_executor...")
        from api.workflow.cell.executor import CellExecutor  # noqa: F401
        print("  OK")

        print("Importing updated models...")
        from api.workflow.models import WorkflowCell, WorkflowPlan, CellStatus  # noqa: F401
        print("  OK")

        print("Importing response models...")
        from api.models import CellResponse, WorkflowPlanResponse, CellBasedWorkflowResponse  # noqa: F401
        print("  OK")

        print("\nAll imports successful!")
        return True

    except Exception as e:
        print("\nImport Error: {}".format(str(e)))
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("CELL-BASED WORKFLOW ARCHITECTURE TESTS")
    print("=" * 60)

    # Test 0: Syntax check
    if not await test_syntax_check():
        print("\nSyntax check failed. Fix import errors before continuing.")
        sys.exit(1)

    # Test 1: Create workflow
    workflow_id = await test_create_cell_based_workflow()

    if not workflow_id:
        print("\nFailed to create workflow. Make sure the server is running.")
        print("Start the server with: cd workflowbuilder && python -m uvicorn api.main:app --reload")
        sys.exit(1)

    # Test 2: Get plan
    await test_get_workflow_plan(workflow_id)

    # Test 3: Execute with streaming
    print("\nNote: Test 3 will execute the workflow and make actual API calls.")
    print("This may take 30-60 seconds depending on the workflow complexity.")

    proceed = input("\nRun execution test? (y/n): ").strip().lower()
    if proceed == 'y':
        await test_execute_stream(workflow_id)
    else:
        print("Skipped execution test.")

    print("\n" + "=" * 60)
    print("TESTS COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
