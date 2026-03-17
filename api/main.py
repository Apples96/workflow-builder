"""
Main FastAPI Application for Workflow Automation System

This is the core FastAPI application that provides REST API endpoints for:
- Creating workflows from natural language descriptions
- Executing workflows with user input and file attachments
- Managing file uploads and processing
- Handling workflow feedback and regeneration

Key Features:
    - AI-powered workflow generation using Anthropic Claude
    - Document processing via LightOn Paradigm API
    - File upload and management
    - Real-time workflow execution with timeout handling
    - Comprehensive CORS support for web frontends
    - Error handling and logging

API Endpoints:
    - POST /workflows - Create new workflow
    - GET /workflows/{id} - Get workflow details
    - POST /workflows/{id}/execute - Execute workflow
    - POST /files/upload - Upload files for processing
    - File management endpoints for questioning and deletion

The application supports cross-domain deployment with multiple frontend origins
and provides comprehensive API documentation via FastAPI's automatic OpenAPI integration.
"""

import logging
import asyncio
import json
import re
import time
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response, StreamingResponse
import uvicorn

from .config import settings
from .models import (
    WorkflowCreateRequest,
    WorkflowExecuteRequest,
    ErrorResponse,
    FileUploadResponse,
    FileInfoResponse,
    WorkflowDescriptionEnhanceRequest,
    WorkflowDescriptionEnhanceResponse,
    CellBasedWorkflowResponse,
    CellBasedExecuteRequest,
    CellResponse,
    WorkflowPlanResponse,
    CellStatusEnum,
    CellFeedbackRequest,
    CellExecuteSingleRequest,
    ExecuteWithEvaluationRequest,
    SuccessCriteriaRequest,
)
from .workflow.core.enhancer import WorkflowEnhancer
from .workflow.core.executor import workflow_executor
from .workflow.models import Workflow, WorkflowExecution, ExecutionStatus, WorkflowPlan, WorkflowCell, CellStatus
from .workflow.cell.planner import WorkflowPlanner
from .workflow.cell.executor import CellExecutor
from .paradigm_client import ParadigmClient, paradigm_client

# Configure logging based on debug settings
logging.basicConfig(level=logging.INFO if settings.debug else logging.WARNING)
logger = logging.getLogger(__name__)

# =============================================================================
# EXECUTION STATE TRACKING
# Tracks active workflow executions and their cancellation status
# =============================================================================

# Dictionary mapping workflow_id -> execution state
# State: {"cancelled": bool, "started_at": datetime, "status": str}
active_executions: Dict[str, Dict[str, Any]] = {}


def is_execution_cancelled(workflow_id: str) -> bool:
    """Check if execution for a workflow has been cancelled."""
    state = active_executions.get(workflow_id)
    return state.get("cancelled", False) if state else False


def mark_execution_started(workflow_id: str):
    """Mark a workflow execution as started."""
    active_executions[workflow_id] = {
        "cancelled": False,
        "started_at": datetime.utcnow(),
        "status": "running"
    }


def mark_execution_cancelled(workflow_id: str):
    """Mark a workflow execution as cancelled."""
    if workflow_id in active_executions:
        active_executions[workflow_id]["cancelled"] = True
        active_executions[workflow_id]["status"] = "cancelled"


def mark_execution_completed(workflow_id: str):
    """Mark a workflow execution as completed and clean up."""
    if workflow_id in active_executions:
        del active_executions[workflow_id]


def get_execution_status(workflow_id: str) -> Optional[Dict[str, Any]]:
    """Get the current execution status for a workflow."""
    return active_executions.get(workflow_id)


# API key validation helpers
def validate_anthropic_api_key():
    """
    Validate that Anthropic API key is available.

    Returns:
        bool: True if API key is available

    Raises:
        HTTPException: 503 if API key is missing
    """
    if not settings.anthropic_api_key:
        raise HTTPException(
            status_code=503,
            detail="Anthropic API key not configured. Please set ANTHROPIC_API_KEY environment variable."
        )
    return True

def get_paradigm_api_key(request: Request) -> str:
    """
    Extract Paradigm API key from request header or query param (for SSE).

    Users provide their own Paradigm API key via the frontend.
    Falls back to server-side .env key for development convenience.

    Args:
        request: The incoming FastAPI request

    Returns:
        str: The Paradigm API key

    Raises:
        HTTPException: 401 if no API key is found
    """
    api_key = (
        request.headers.get("X-Paradigm-Api-Key")
        or request.query_params.get("api_key")
        or settings.lighton_api_key
    )
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Paradigm API key required. Please enter your API key in the settings bar."
        )
    return api_key

# Create FastAPI app with comprehensive metadata
app = FastAPI(
    title="Workflow Automation API",
    description="API for creating and executing automated workflows using AI",
    version="1.0.0",
    debug=settings.debug
)

# Create API router with /api prefix
from fastapi import APIRouter
api_router = APIRouter()

# Add CORS middleware for cross-domain frontend support
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "null",  # Allow file:// protocol for local HTML testing
        "http://localhost:3000",  # Local development
        "http://127.0.0.1:3000",
        "https://scaffold-ai-test2.vercel.app",  # Production frontend
        "https://scaffold-ai-test2-milo-rignells-projects.vercel.app",  # Your current deployment
        "https://scaffold-ai-test2-fi4dvy1xl-milo-rignells-projects.vercel.app",
        "https://scaffold-ai-test2-tawny.vercel.app",  # Your other deployment
        "https://scaffold-ai-test2-git-main-milo-rignells-projects.vercel.app/",
        "https://*.vercel.app",  # All Vercel deployments
        "https://*.netlify.app",  # Netlify deployments
        "https://*.github.io",   # GitHub Pages
        "https://*.surge.sh",    # Surge deployments
        "https://*.firebaseapp.com"  # Firebase hosting
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse, tags=["Frontend"])
async def serve_frontend():
    """
    Serve the frontend HTML page.

    Returns the main application interface when accessing the root URL.
    Cache-Control headers prevent browser caching issues.
    """
    try:
        # Try to read the index.html file from the project root
        with open("index.html", "r", encoding="utf-8") as f:
            content = f.read()
        # Add cache-control headers to prevent browser caching issues
        return HTMLResponse(
            content=content,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    except FileNotFoundError:
        # Fallback to API info if index.html not found
        return {
            "message": "Workflow Automation API",
            "version": "1.0.0",
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "note": "Frontend file not found - API only mode"
        }

@app.get("/lighton-logo.png", tags=["Static"])
async def serve_logo():
    """
    Serve the LightOn logo image.
    """
    try:
        with open("lighton-logo.png", "rb") as f:
            image_data = f.read()
        return Response(content=image_data, media_type="image/png")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Logo not found")

@app.get("/health", tags=["Health"]) 
async def health_check():
    """
    Health check endpoint for monitoring.
    
    Provides service status information for deployment platforms.
    """
    return {
        "message": "Workflow Automation API",
        "version": "1.0.0",
        "status": "healthy", 
        "timestamp": datetime.utcnow().isoformat()
    }

@api_router.post("/workflows/enhance-description", response_model=WorkflowDescriptionEnhanceResponse, tags=["Workflows"])
async def enhance_workflow_description(request: WorkflowDescriptionEnhanceRequest):
    """
    Enhance a raw workflow description using Claude AI.
    
    Takes a user's initial natural language workflow description and transforms it
    into a detailed, actionable workflow specification with clear steps, proper
    tool usage, and identification of any missing information or limitations.
    
    Args:
        request: Enhancement request containing the raw workflow description
        
    Returns:
        WorkflowDescriptionEnhanceResponse: Enhanced description with questions and warnings
        
    Raises:
        HTTPException: 503 if API keys are missing, 500 if enhancement fails
        
    Example:
        POST /workflows/enhance-description
        {
            "description": "Search for documents and analyze them"
        }
        
        Returns enhanced description with specific steps and tool usage details.
    """
    # Validate required API keys
    validate_anthropic_api_key()
    
    try:
        logger.info("Enhancing workflow description: {}...".format(request.description[:100]))

        # Enhance the description using the enhancer directly
        from .clients import create_anthropic_client
        enhancer = WorkflowEnhancer(create_anthropic_client())
        result = await enhancer.enhance_workflow_description(
            request.description,
            output_example=request.output_example
        )

        logger.info("Workflow description enhanced successfully")

        return WorkflowDescriptionEnhanceResponse(
            enhanced_description=result["enhanced_description"],
            questions=result["questions"],
            warnings=result["warnings"]
        )

    except Exception as e:
        logger.error("Failed to enhance workflow description: {}".format(str(e)))
        raise HTTPException(
            status_code=500,
            detail="Failed to enhance workflow description: {}".format(str(e))
        )

# ============================================================================
# Cell-Based Workflow Endpoints
# ============================================================================

@api_router.post("/workflows-cell-based", response_model=CellBasedWorkflowResponse, tags=["Cell-Based Workflows"])
async def create_cell_based_workflow(request: WorkflowCreateRequest):
    """
    Create a new cell-based workflow with step-by-step execution plan.

    This endpoint creates a workflow that will be executed cell-by-cell,
    with each cell's output displayed as it completes. The workflow is
    broken into discrete steps during the planning phase.

    Args:
        request: Workflow creation request with description and optional context

    Returns:
        CellBasedWorkflowResponse: Workflow with plan and cell definitions

    Raises:
        HTTPException: 503 if API keys missing, 500 if planning fails
    """
    validate_anthropic_api_key()

    try:
        logger.info("Creating cell-based workflow: {}...".format(request.description[:100]))

        # Create the workflow planner
        planner = WorkflowPlanner()

        # Generate the plan with optional output example for deriving final cell criteria
        plan = await planner.create_plan(
            description=request.description,
            context=request.context,
            output_example=request.output_example
        )

        # Create workflow object with output_example stored in context for later use in evaluation
        workflow_context = request.context or {}
        if request.output_example:
            workflow_context["output_example"] = request.output_example

        # Auto-generate a name from the description if none provided
        workflow_name = request.name
        if not workflow_name:
            # Take the first sentence or first 60 chars, whichever is shorter
            desc = request.description.strip()
            for sep in ['.', '\n', '!']:
                first_sentence = desc.split(sep)[0].strip()
                if len(first_sentence) < len(desc):
                    desc = first_sentence
                    break
            workflow_name = desc[:60].rstrip(' .,;:!-')

        # Create workflow object
        workflow = Workflow(
            name=workflow_name,
            description=request.description,
            status="ready",
            context=workflow_context
        )

        # Store the plan with the workflow
        plan.workflow_id = workflow.id
        for cell in plan.cells:
            cell.workflow_id = workflow.id

        # Store workflow in executor (for retrieval)
        workflow_executor.store_workflow(workflow)

        # Store the plan separately
        workflow_executor.store_workflow_plan(workflow.id, plan)

        logger.info("Cell-based workflow created: {} with {} cells".format(
            workflow.id, len(plan.cells)
        ))

        # Build response
        cells_response = [
            CellResponse(
                id=cell.id,
                step_number=cell.step_number,
                name=cell.name,
                description=cell.description,
                layer=cell.layer,
                sublayer_index=cell.sublayer_index,
                display_step=cell.get_display_step(),
                depends_on=cell.depends_on,
                status=CellStatusEnum(cell.status.value),
                inputs_required=cell.inputs_required,
                outputs_produced=cell.outputs_produced,
                paradigm_tools_used=cell.paradigm_tools_used,
                generated_code=cell.generated_code,
                code_description=cell.code_description,
                success_criteria=cell.success_criteria,
                output=cell.output,
                execution_time=cell.execution_time,
                error=cell.error
            )
            for cell in plan.cells
        ]

        plan_response = WorkflowPlanResponse(
            id=plan.id,
            total_cells=len(plan.cells),
            total_layers=plan.get_max_layer(),
            is_parallel=plan.is_parallel_workflow(),
            cells=cells_response,
            shared_context_schema=plan.shared_context_schema,
            status=plan.status
        )

        return CellBasedWorkflowResponse(
            id=workflow.id,
            name=workflow.name,
            description=workflow.description,
            status=workflow.status,
            execution_mode="cell_based",
            plan=plan_response,
            cells=cells_response,
            generated_code=None,
            created_at=workflow.created_at,
            updated_at=workflow.updated_at,
            error=workflow.error
        )

    except Exception as e:
        logger.error("Failed to create cell-based workflow: {}".format(str(e)))
        raise HTTPException(
            status_code=500,
            detail="Failed to create cell-based workflow: {}".format(str(e))
        )


@api_router.post("/workflows/{workflow_id}/execute-stream", tags=["Cell-Based Workflows"])
async def execute_workflow_stream(workflow_id: str, request: CellBasedExecuteRequest, raw_request: Request):
    """
    Execute a cell-based workflow with real-time streaming of results.

    This endpoint executes the workflow cell-by-cell, streaming events
    via Server-Sent Events as each cell generates, executes, and completes.
    Each cell's output is displayed progressively to the user.

    Event Types:
        - workflow_start: Workflow execution beginning
        - cell_generating: Claude is generating code for a cell
        - cell_ready: Cell code generated successfully
        - cell_executing: Cell is now running
        - cell_completed: Cell finished with output
        - cell_failed: Cell execution failed
        - workflow_completed: All cells finished successfully
        - workflow_failed: Workflow stopped due to cell failure

    Args:
        workflow_id: ID of the workflow to execute
        request: Execution request with user input and optional file IDs

    Returns:
        StreamingResponse: SSE stream of execution events
    """
    validate_anthropic_api_key()
    api_key = get_paradigm_api_key(raw_request)

    async def event_generator():
        try:
            # Get the workflow
            workflow = workflow_executor.get_workflow(workflow_id)
            if not workflow:
                yield "data: {}\n\n".format(json.dumps({
                    "type": "error",
                    "error": "Workflow not found: {}".format(workflow_id)
                }))
                return

            # Get the plan
            plan = workflow_executor.get_workflow_plan(workflow_id)
            if not plan:
                yield "data: {}\n\n".format(json.dumps({
                    "type": "error",
                    "error": "Workflow plan not found. This may be a monolithic workflow."
                }))
                return

            # Check if this is a parallel workflow
            is_parallel = plan.is_parallel_workflow()

            logger.info("Starting {} execution for workflow: {} ({} layers, {} cells)".format(
                "PARALLEL" if is_parallel else "sequential",
                workflow_id,
                plan.get_max_layer(),
                len(plan.cells)
            ))

            # Create cell executor with per-user API key
            executor = CellExecutor(paradigm_api_key=api_key)

            # Use parallel execution if workflow has parallel layers, otherwise sequential
            if is_parallel:
                async for event in executor.execute_workflow_parallel(
                    plan=plan,
                    user_input=request.user_input,
                    attached_file_ids=request.attached_file_ids,
                    workflow_description=workflow.description
                ):
                    yield "data: {}\n\n".format(json.dumps(event))
            else:
                async for event in executor.execute_workflow_stepwise(
                    plan=plan,
                    user_input=request.user_input,
                    attached_file_ids=request.attached_file_ids,
                    workflow_description=workflow.description
                ):
                    yield "data: {}\n\n".format(json.dumps(event))

        except Exception as e:
            logger.error("Streaming execution error: {}".format(str(e)))
            yield "data: {}\n\n".format(json.dumps({
                "type": "error",
                "error": str(e)
            }))

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )


@api_router.post("/workflows/{workflow_id}/execute-parallel", tags=["Cell-Based Workflows"])
async def execute_workflow_parallel(workflow_id: str, request: CellBasedExecuteRequest, raw_request: Request):
    """
    Execute a cell-based workflow with layer-based parallelization.

    This endpoint executes the workflow using parallel layer execution:
    - Cells in the same layer execute concurrently
    - Each cell has its own retry + evaluation cycle
    - Layer N+1 only starts after ALL cells in layer N complete
    - Context is merged from all parallel cells before next layer

    Event Types:
        Layer events:
            - layer_started: Beginning of layer execution
            - layer_completed: All cells in layer finished
            - layer_failed: One or more cells in layer failed

        Cell events:
            - cell_generating: Claude is generating code for a cell
            - cell_ready: Cell code generated successfully
            - cell_executing: Cell is now running
            - cell_evaluating: LLM evaluation of output
            - cell_evaluation_passed: Output passed evaluation
            - cell_evaluation_failed: Output failed, will retry
            - cell_completed: Cell finished with output
            - cell_failed: Cell execution failed

        Workflow events:
            - workflow_start: Workflow execution beginning
            - workflow_completed: All layers finished successfully
            - workflow_failed: Workflow stopped due to layer failure

    Args:
        workflow_id: ID of the workflow to execute
        request: Execution request with user input and optional file IDs

    Returns:
        StreamingResponse: SSE stream of execution events
    """
    validate_anthropic_api_key()
    api_key = get_paradigm_api_key(raw_request)

    async def event_generator():
        try:
            # Get the workflow
            workflow = workflow_executor.get_workflow(workflow_id)
            if not workflow:
                yield "data: {}\n\n".format(json.dumps({
                    "type": "error",
                    "error": "Workflow not found: {}".format(workflow_id)
                }))
                return

            # Get the plan
            plan = workflow_executor.get_workflow_plan(workflow_id)
            if not plan:
                yield "data: {}\n\n".format(json.dumps({
                    "type": "error",
                    "error": "Workflow plan not found. This may be a monolithic workflow."
                }))
                return

            # Check if this is a parallel workflow
            is_parallel = plan.is_parallel_workflow()

            logger.info("Starting {} execution for workflow: {} ({} layers, {} cells)".format(
                "parallel" if is_parallel else "sequential",
                workflow_id,
                plan.get_max_layer(),
                len(plan.cells)
            ))

            # Create cell executor with per-user API key
            executor = CellExecutor(paradigm_api_key=api_key)

            if is_parallel:
                # Use parallel execution
                async for event in executor.execute_workflow_parallel(
                    plan=plan,
                    user_input=request.user_input,
                    attached_file_ids=request.attached_file_ids,
                    workflow_description=workflow.description
                ):
                    yield "data: {}\n\n".format(json.dumps(event))
            else:
                # Fall back to sequential execution for non-parallel workflows
                async for event in executor.execute_workflow_stepwise(
                    plan=plan,
                    user_input=request.user_input,
                    attached_file_ids=request.attached_file_ids,
                    workflow_description=workflow.description
                ):
                    yield "data: {}\n\n".format(json.dumps(event))

        except Exception as e:
            logger.error("Parallel execution error: {}".format(str(e)))
            yield "data: {}\n\n".format(json.dumps({
                "type": "error",
                "error": str(e)
            }))

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )


@api_router.post("/workflows/{workflow_id}/execute-with-evaluation", tags=["Cell-Based Workflows"])
async def execute_workflow_with_evaluation(workflow_id: str, request: ExecuteWithEvaluationRequest, raw_request: Request):
    """
    Execute a cell-based workflow with LLM-as-judge evaluation.

    Uses the smoke test approach for quality assurance:
    1. For each cell, execute with the first example (smoke test)
    2. Evaluate the output using Claude as a judge
    3. If evaluation fails, fix the code and retry (up to 5 times)
    4. Once evaluation passes (or max retries reached), run remaining examples
    5. Move to next cell

    This ensures each cell produces valid output before running all examples.

    Event Types:
        Standard events: workflow_start, cell_generating, cell_ready,
                        cell_executing, cell_completed, cell_failed,
                        workflow_completed, workflow_failed

        Evaluation events:
            - cell_smoke_test_completed: First example executed successfully
            - cell_evaluating: Starting LLM evaluation of output
            - cell_evaluation_passed: Output passed evaluation
            - cell_evaluation_failed: Output failed evaluation, will retry
            - cell_evaluation_max_retries: Max retries reached, proceeding anyway
            - cell_fixing_from_evaluation: Fixing code based on evaluation feedback
            - cell_code_fixed: Code was fixed (for execution or evaluation error)
            - cell_example_completed: An example completed for a cell
            - cell_example_failed: An example failed for a cell

    Args:
        workflow_id: ID of the workflow to execute
        request: ExecuteWithEvaluationRequest with list of examples

    Returns:
        StreamingResponse: SSE stream of execution events
    """
    validate_anthropic_api_key()
    api_key = get_paradigm_api_key(raw_request)

    async def event_generator():
        try:
            # Get the workflow
            workflow = workflow_executor.get_workflow(workflow_id)
            if not workflow:
                yield "data: {}\n\n".format(json.dumps({
                    "type": "error",
                    "error": "Workflow not found: {}".format(workflow_id)
                }))
                return

            # Get the plan
            plan = workflow_executor.get_workflow_plan(workflow_id)
            if not plan:
                yield "data: {}\n\n".format(json.dumps({
                    "type": "error",
                    "error": "Workflow plan not found. This may be a monolithic workflow."
                }))
                return

            logger.info("Starting execution with evaluation for workflow: {} with {} examples".format(
                workflow_id, len(request.examples)
            ))

            # Mark execution as started (for stop functionality)
            mark_execution_started(workflow_id)

            # Convert examples to the format expected by the executor
            examples = [
                {
                    "id": example.id or "example_{}".format(i),
                    "user_input": example.user_input,
                    "attached_file_ids": example.attached_file_ids or []
                }
                for i, example in enumerate(request.examples)
            ]

            # Create cell executor with per-user API key
            executor = CellExecutor(paradigm_api_key=api_key)
            async for event in executor.execute_workflow_with_evaluation(
                plan=plan,
                examples=examples,
                workflow_description=workflow.description
            ):
                # Check if execution was cancelled
                if is_execution_cancelled(workflow_id):
                    yield "data: {}\n\n".format(json.dumps({
                        "type": "workflow_stopped",
                        "message": "Execution stopped by user",
                        "timestamp": datetime.utcnow().isoformat()
                    }))
                    mark_execution_completed(workflow_id)
                    return

                yield "data: {}\n\n".format(json.dumps(event))

                # If workflow completed or failed, clean up tracking
                if event.get("type") in ["workflow_completed", "workflow_failed"]:
                    mark_execution_completed(workflow_id)

        except Exception as e:
            logger.error("Execution with evaluation error: {}".format(str(e)))
            mark_execution_completed(workflow_id)
            yield "data: {}\n\n".format(json.dumps({
                "type": "error",
                "error": str(e)
            }))

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )


@api_router.post("/workflows/{workflow_id}/stop", tags=["Cell-Based Workflows"])
async def stop_workflow_execution(workflow_id: str):
    """
    Stop an in-progress workflow execution.

    Cancels the execution after the current cell/layer completes.
    The workflow can be re-run after stopping.

    Args:
        workflow_id: ID of the workflow to stop

    Returns:
        dict: Confirmation of cancellation request
    """
    execution_state = get_execution_status(workflow_id)

    if not execution_state:
        return {
            "success": False,
            "message": "No active execution found for this workflow",
            "workflow_id": workflow_id
        }

    if execution_state.get("cancelled"):
        return {
            "success": True,
            "message": "Execution already cancelled",
            "workflow_id": workflow_id
        }

    mark_execution_cancelled(workflow_id)
    logger.info(f"Execution cancelled for workflow: {workflow_id}")

    return {
        "success": True,
        "message": "Execution will stop after current cell completes",
        "workflow_id": workflow_id
    }


@api_router.get("/workflows/{workflow_id}/execution-status", tags=["Cell-Based Workflows"])
async def get_workflow_execution_status(workflow_id: str):
    """
    Get the current execution status of a workflow.

    Returns whether the workflow is currently executing, stopped, or idle.

    Args:
        workflow_id: ID of the workflow

    Returns:
        dict: Current execution status
    """
    execution_state = get_execution_status(workflow_id)

    if not execution_state:
        return {
            "workflow_id": workflow_id,
            "is_executing": False,
            "status": "idle"
        }

    return {
        "workflow_id": workflow_id,
        "is_executing": execution_state.get("status") == "running",
        "status": execution_state.get("status"),
        "started_at": execution_state.get("started_at").isoformat() if execution_state.get("started_at") else None,
        "cancelled": execution_state.get("cancelled", False)
    }


@api_router.get("/workflows/{workflow_id}/plan", response_model=WorkflowPlanResponse, tags=["Cell-Based Workflows"])
async def get_workflow_plan(workflow_id: str):
    """
    Retrieve the execution plan for a cell-based workflow.

    Returns the plan with all cell definitions, their status,
    and any outputs from completed cells.

    Args:
        workflow_id: ID of the workflow

    Returns:
        WorkflowPlanResponse: The workflow plan with cells

    Raises:
        HTTPException: 404 if workflow or plan not found
    """
    try:
        workflow = workflow_executor.get_workflow(workflow_id)
        if not workflow:
            raise HTTPException(
                status_code=404,
                detail="Workflow not found: {}".format(workflow_id)
            )

        plan = workflow_executor.get_workflow_plan(workflow_id)
        if not plan:
            raise HTTPException(
                status_code=404,
                detail="Plan not found for workflow: {}".format(workflow_id)
            )

        cells_response = [
            CellResponse(
                id=cell.id,
                step_number=cell.step_number,
                name=cell.name,
                description=cell.description,
                layer=cell.layer,
                sublayer_index=cell.sublayer_index,
                display_step=cell.get_display_step(),
                depends_on=cell.depends_on,
                status=CellStatusEnum(cell.status.value),
                inputs_required=cell.inputs_required,
                outputs_produced=cell.outputs_produced,
                paradigm_tools_used=cell.paradigm_tools_used,
                generated_code=cell.generated_code,
                code_description=cell.code_description,
                success_criteria=cell.success_criteria,
                output=cell.output,
                execution_time=cell.execution_time,
                error=cell.error
            )
            for cell in plan.cells
        ]

        return WorkflowPlanResponse(
            id=plan.id,
            total_cells=len(plan.cells),
            total_layers=plan.get_max_layer(),
            is_parallel=plan.is_parallel_workflow(),
            cells=cells_response,
            shared_context_schema=plan.shared_context_schema,
            status=plan.status
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get workflow plan: {}".format(str(e)))
        raise HTTPException(
            status_code=500,
            detail="Failed to get workflow plan: {}".format(str(e))
        )


@api_router.post("/workflows/{workflow_id}/cells/{cell_id}/approve", tags=["Cell-Based Workflows"])
async def approve_cell(workflow_id: str, cell_id: str):
    """
    Approve a completed cell's output and allow workflow to continue.

    This endpoint is called when the user approves a cell's generated code
    and output. It simply acknowledges the approval - workflow execution
    will naturally continue to the next cell.

    Args:
        workflow_id: ID of the workflow
        cell_id: ID of the cell to approve

    Returns:
        dict: Success status and message

    Raises:
        HTTPException: 404 if workflow or cell not found
    """
    try:
        logger.info("Cell approved by user: {} in workflow {}".format(cell_id, workflow_id))

        # Verify workflow exists
        workflow = workflow_executor.get_workflow(workflow_id)
        if not workflow:
            raise HTTPException(
                status_code=404,
                detail="Workflow not found: {}".format(workflow_id)
            )

        return {
            "success": True,
            "message": "Cell {} approved successfully".format(cell_id)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to approve cell: {}".format(str(e)))
        raise HTTPException(
            status_code=500,
            detail="Failed to approve cell: {}".format(str(e))
        )


@api_router.post("/workflows/{workflow_id}/cells/{cell_id}/rerun", tags=["Cell-Based Workflows"])
async def rerun_cell(workflow_id: str, cell_id: str, raw_request: Request):
    """
    Rerun a specific cell with its current code and the latest execution context.

    This endpoint allows users to rerun a cell after modifying its code or when
    they want to refresh its outputs. The cell executes with the current shared
    context (outputs from all previous cells), and its outputs are updated in
    the context. Later cells that depend on this cell's outputs will use the
    updated values when they execute.

    Args:
        workflow_id: ID of the workflow
        cell_id: ID of the cell to rerun

    Returns:
        dict: Execution results with new outputs and formatted variable values

    Raises:
        HTTPException: 404 if workflow or cell not found, 500 if execution fails
    """
    api_key = get_paradigm_api_key(raw_request)

    try:
        logger.info("Rerunning cell {} in workflow {}".format(cell_id, workflow_id))

        # Verify workflow exists
        workflow = workflow_executor.get_workflow(workflow_id)
        if not workflow:
            raise HTTPException(
                status_code=404,
                detail="Workflow not found: {}".format(workflow_id)
            )

        # Get workflow plan
        plan = workflow_executor.get_workflow_plan(workflow_id)
        if not plan:
            raise HTTPException(
                status_code=404,
                detail="Plan not found for workflow: {}".format(workflow_id)
            )

        # Find the cell in the plan
        cell = None
        for c in plan.cells:
            if c.id == cell_id:
                cell = c
                break

        if not cell:
            raise HTTPException(
                status_code=404,
                detail="Cell not found: {}".format(cell_id)
            )

        # Get current execution context
        execution_context = workflow_executor.get_execution_context(workflow_id)

        # If no context exists, initialize with user inputs
        if not execution_context:
            execution_context = {
                "user_input": "",
                "attached_file_ids": []
            }
            logger.warning("No execution context found, using empty context")

        # Execute the cell with per-user API key
        executor = CellExecutor(paradigm_api_key=api_key)

        try:
            import asyncio
            cell_result = await asyncio.wait_for(
                executor._execute_cell_code(
                    cell.generated_code,
                    execution_context,
                    cell.id
                ),
                timeout=executor.max_cell_execution_time
            )

            # Extract outputs
            output_variables = cell_result.get("variables", {})
            output_text = cell_result.get("output", "")

            # Update execution context with new outputs
            execution_context.update(output_variables)
            workflow_executor.store_execution_context(workflow_id, execution_context)

            # Format outputs for display
            formatted_outputs = executor._format_output_variables(output_variables)

            # Update the cell in the plan
            cell.mark_completed(
                output=output_text,
                variables=output_variables,
                execution_time=0
            )
            workflow_executor.update_workflow_plan(workflow_id, plan)

            logger.info("Successfully reran cell {} with {} outputs".format(
                cell_id, len(output_variables)
            ))

            return {
                "success": True,
                "output": output_text,
                "variables": list(output_variables.keys()),
                "variable_values": formatted_outputs,
                "code": cell.generated_code
            }

        except asyncio.TimeoutError:
            error_msg = "Cell execution timed out after {}s".format(
                executor.max_cell_execution_time
            )
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to rerun cell: {}".format(str(e)))
        raise HTTPException(
            status_code=500,
            detail="Failed to rerun cell: {}".format(str(e))
        )


@api_router.post("/workflows/{workflow_id}/cells/{cell_id}/execute-single", tags=["Cell-Based Workflows"])
async def execute_single_cell(
    workflow_id: str,
    cell_id: str,
    request: CellExecuteSingleRequest,
    raw_request: Request
):
    """
    Execute a single cell with provided input and context.

    This endpoint allows executing one cell at a time with specific user input,
    which is useful for multi-example testing where we want to run each cell
    for all examples before moving to the next cell.

    Args:
        workflow_id: ID of the workflow
        cell_id: ID of the cell to execute
        request: CellExecuteSingleRequest with user input, files, and context

    Returns:
        dict: Execution results with outputs and variable values

    Raises:
        HTTPException: 404 if workflow or cell not found, 500 if execution fails
    """
    # Validate API keys upfront since we may need to generate code
    validate_anthropic_api_key()
    api_key = get_paradigm_api_key(raw_request)

    try:
        logger.info("Executing single cell {} in workflow {} with input: {}".format(
            cell_id, workflow_id, request.user_input[:50] if request.user_input else "(empty)"
        ))

        # Verify workflow exists
        workflow = workflow_executor.get_workflow(workflow_id)
        if not workflow:
            raise HTTPException(
                status_code=404,
                detail="Workflow not found: {}".format(workflow_id)
            )

        # Get workflow plan
        plan = workflow_executor.get_workflow_plan(workflow_id)
        if not plan:
            raise HTTPException(
                status_code=404,
                detail="Plan not found for workflow: {}".format(workflow_id)
            )

        # Find the cell in the plan
        cell = None
        for c in plan.cells:
            if c.id == cell_id:
                cell = c
                break

        if not cell:
            raise HTTPException(
                status_code=404,
                detail="Cell not found: {}".format(cell_id)
            )

        # Initialize context with user input
        context = {
            "user_input": request.user_input,
            "attached_file_ids": request.attached_file_ids or []
        }

        # Merge in any provided execution context from previous cells
        if request.execution_context:
            context.update(request.execution_context)

        # Execute the cell with per-user API key
        executor = CellExecutor(paradigm_api_key=api_key)

        # Generate code for the cell if it hasn't been generated yet
        if not cell.generated_code:
            logger.info("Cell {} has no generated code, generating now...".format(cell_id))
            try:
                description, code = await executor.cell_generator.generate_cell_code(
                    cell=cell,
                    available_context=plan.shared_context_schema or {},
                    workflow_description=workflow.description
                )
                cell.mark_ready(code, description)
                # Update the plan with the generated code
                workflow_executor.update_workflow_plan(workflow_id, plan)
                logger.info("Generated code for cell {} ({} chars)".format(cell_id, len(code)))
            except Exception as gen_error:
                logger.error("Failed to generate code for cell {}: {}".format(cell_id, str(gen_error)))
                raise HTTPException(
                    status_code=500,
                    detail="Failed to generate code for cell: {}".format(str(gen_error))
                )

        try:
            import asyncio
            cell_result = await asyncio.wait_for(
                executor._execute_cell_code(
                    cell.generated_code,
                    context,
                    cell.id
                ),
                timeout=executor.max_cell_execution_time
            )

            # Extract outputs
            output_variables = cell_result.get("variables", {})
            output_text = cell_result.get("output", "")

            # Format outputs for display
            formatted_outputs = executor._format_output_variables(output_variables)

            logger.info("Successfully executed cell {} with {} outputs".format(
                cell_id, len(output_variables)
            ))

            return {
                "success": True,
                "output": output_text,
                "variables": list(output_variables.keys()),
                "variable_values": formatted_outputs,
                "output_variables": output_variables,  # Raw variables for next cell's context
                "code": cell.generated_code
            }

        except asyncio.TimeoutError:
            error_msg = "Cell execution timed out after {}s".format(
                executor.max_cell_execution_time
            )
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

        except Exception as e:
            logger.error("Cell execution failed: {}".format(str(e)))
            raise HTTPException(
                status_code=500,
                detail="Cell execution failed: {}".format(str(e))
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to execute single cell: {}".format(str(e)))
        raise HTTPException(
            status_code=500,
            detail="Failed to execute single cell: {}".format(str(e))
        )


@api_router.post("/workflows/{workflow_id}/cells/{cell_id}/feedback", tags=["Cell-Based Workflows"])
async def submit_cell_feedback(workflow_id: str, cell_id: str, request: CellFeedbackRequest, raw_request: Request):
    """
    Submit feedback for a cell and regenerate its code based on user input.

    This endpoint takes user feedback about a cell's generated code and uses
    Claude to regenerate the code incorporating the feedback. All necessary
    context is provided to Claude including the original cell plan, previous
    code, and user feedback.

    Args:
        workflow_id: ID of the workflow
        cell_id: ID of the cell to regenerate
        request: CellFeedbackRequest with user feedback

    Returns:
        dict: New generated code and status

    Raises:
        HTTPException: 400 if feedback missing, 404 if workflow/cell not found
    """
    try:
        feedback = request.feedback.strip()

        logger.info("Received feedback for cell {} in workflow {}: {}".format(
            cell_id, workflow_id, feedback[:100]
        ))

        # Verify workflow exists
        workflow = workflow_executor.get_workflow(workflow_id)
        if not workflow:
            raise HTTPException(
                status_code=404,
                detail="Workflow not found: {}".format(workflow_id)
            )

        # Get workflow plan
        plan = workflow_executor.get_workflow_plan(workflow_id)
        if not plan:
            raise HTTPException(
                status_code=404,
                detail="Plan not found for workflow: {}".format(workflow_id)
            )

        # Find the cell in the plan
        cell = None
        for c in plan.cells:
            if c.id == cell_id:
                cell = c
                break

        if not cell:
            raise HTTPException(
                status_code=404,
                detail="Cell not found: {}".format(cell_id)
            )

        # Regenerate the cell code with feedback (pass API key for consistency)
        api_key = get_paradigm_api_key(raw_request)
        executor = CellExecutor(paradigm_api_key=api_key)

        # Build comprehensive feedback context message for Claude
        feedback_context = """CELL DESCRIPTION:
{cell_description}

USER FEEDBACK ON CODE:
{feedback}

INSTRUCTIONS:
Please regenerate the complete cell code incorporating the user's feedback above.
- Address all points in the user's feedback
- Maintain the same inputs and outputs as specified in the cell plan
- Follow all coding guidelines and best practices from the cell generation prompt
- Keep the code standalone with full API documentation""".format(
            cell_description=cell.description or "No description available",
            feedback=feedback
        )

        # Use the executor's fix_cell_code method
        # This method already handles Claude integration and prompt loading properly
        new_code = await executor.fix_cell_code(
            cell=cell,
            failed_code=cell.generated_code or "",
            error_message=feedback_context,
            execution_context=plan.shared_context_schema or {},
            workflow_description=workflow.description,
            attempt_number=1
        )

        if not new_code:
            raise Exception("Failed to regenerate code with feedback")

        # Update the cell with new code
        cell.generated_code = new_code
        cell.status = CellStatus.READY

        # Persist the updated plan so the new code is available for future reruns
        workflow_executor.update_workflow_plan(workflow_id, plan)

        logger.info("Successfully regenerated code for cell {} with user feedback".format(cell_id))

        return {
            "success": True,
            "message": "Cell code regenerated successfully",
            "new_code": new_code
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to process cell feedback: {}".format(str(e)))
        raise HTTPException(
            status_code=500,
            detail="Failed to process cell feedback: {}".format(str(e))
        )


@api_router.post("/workflows/{workflow_id}/cells/{cell_id}/success-criteria", tags=["Cell-Based Workflows"])
async def update_cell_success_criteria(workflow_id: str, cell_id: str, request: SuccessCriteriaRequest):
    """
    Update a cell's success criteria and reset it for re-execution.

    This endpoint allows users to edit the validation criteria for a cell's output.
    After updating, the cell and all dependent cells are reset to 'ready' status
    so they can be re-executed with the new criteria.

    Args:
        workflow_id: ID of the workflow
        cell_id: ID of the cell to update
        request: SuccessCriteriaRequest with the new success criteria

    Returns:
        dict: Success status and cell ID

    Raises:
        HTTPException: 404 if workflow or cell not found, 500 for other errors
    """
    try:
        logger.info("Updating success criteria for cell {} in workflow {}".format(cell_id, workflow_id))

        # Verify workflow exists
        workflow = workflow_executor.get_workflow(workflow_id)
        if not workflow:
            raise HTTPException(
                status_code=404,
                detail="Workflow not found: {}".format(workflow_id)
            )

        # Get workflow plan
        plan = workflow_executor.get_workflow_plan(workflow_id)
        if not plan:
            raise HTTPException(
                status_code=404,
                detail="Plan not found for workflow: {}".format(workflow_id)
            )

        # Find the cell in the plan
        cell = None
        cell_index = -1
        for i, c in enumerate(plan.cells):
            if c.id == cell_id:
                cell = c
                cell_index = i
                break

        if not cell:
            raise HTTPException(
                status_code=404,
                detail="Cell not found: {}".format(cell_id)
            )

        # Update the success criteria
        cell.success_criteria = request.success_criteria

        # Reset cell status to ready (keep code, clear execution results)
        cell.status = CellStatus.READY
        cell.output = None
        cell.output_variables = None
        cell.error = None

        # Reset dependent cells too (cells that depend on this cell or are in later layers)
        for dep_cell in plan.cells:
            if cell_id in dep_cell.depends_on or dep_cell.layer > cell.layer:
                dep_cell.status = CellStatus.READY
                dep_cell.output = None
                dep_cell.output_variables = None
                dep_cell.error = None

        # Persist the updated plan
        workflow_executor.update_workflow_plan(workflow_id, plan)

        logger.info("Successfully updated success criteria for cell {}".format(cell_id))

        return {
            "success": True,
            "cell_id": cell_id,
            "message": "Success criteria updated. Cell and dependent cells reset for re-execution."
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update success criteria: {}".format(str(e)))
        raise HTTPException(
            status_code=500,
            detail="Failed to update success criteria: {}".format(str(e))
        )


# File upload and management endpoints

@api_router.post("/files/upload", response_model=FileUploadResponse, tags=["Files"])
async def upload_file(
    raw_request: Request,
    file: UploadFile = File(...)
):
    """
    Upload a file to Paradigm for document processing and analysis.

    Files are automatically processed, indexed, and made available for use
    in workflows. Uses the POST /api/v2/files endpoint which automatically
    adds files to the user's documents collection.

    Args:
        file: The file to upload (multipart/form-data, max 100MB)

    Returns:
        FileUploadResponse: File metadata including ID, size, and processing status

    Raises:
        HTTPException: 503 if API keys are missing, 500 if upload fails

    Note:
        Files are processed asynchronously. The endpoint waits for embedding
        to complete before returning, ensuring files are fully searchable.
    """
    # Extract per-user Paradigm API key
    api_key = get_paradigm_api_key(raw_request)

    try:
        logger.info(f"Uploading file: {file.filename}")

        # Read file content
        file_content = await file.read()

        # Upload to Paradigm using POST /api/v2/files endpoint
        # Create per-request client with user's API key
        client = ParadigmClient(api_key=api_key)
        result = await client.upload_file(
            file_content=file_content,
            filename=file.filename,
            wait_for_embedding=True
        )
        
        logger.info(f"File uploaded successfully: {result.get('id')}")
        
        return FileUploadResponse(**result)
        
    except Exception as e:
        logger.error(f"Failed to upload file: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload file: {str(e)}"
        )

@api_router.get("/files/{file_id}", response_model=FileInfoResponse, tags=["Files"])
async def get_file_info(file_id: int, raw_request: Request, include_content: bool = False):
    """
    Retrieve metadata and optionally content of an uploaded file.
    
    Provides file information including processing status, size, and creation time.
    Can optionally include the full file content for inspection.
    
    Args:
        file_id: Unique identifier of the file
        include_content: Whether to include file content in response
        
    Returns:
        FileInfoResponse: File metadata and optionally content
        
    Raises:
        HTTPException: 503 if API keys are missing, 500 if retrieval fails
    """
    # Extract per-user Paradigm API key
    api_key = get_paradigm_api_key(raw_request)

    try:
        client = ParadigmClient(api_key=api_key)
        result = await client.get_file(file_id, include_content)
        return FileInfoResponse(**result)
        
    except Exception as e:
        logger.error(f"Failed to get file info for {file_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get file info: {str(e)}"
        )

@api_router.delete("/files/{file_id}", tags=["Files"])
async def delete_file(file_id: int, raw_request: Request):
    """
    Delete an uploaded file from the system.
    
    Permanently removes the file and all associated metadata from Paradigm.
    The file will no longer be available for workflows or questioning.
    
    Args:
        file_id: ID of the file to delete
        
    Returns:
        dict: Success status and confirmation message
        
    Raises:
        HTTPException: 503 if API keys are missing, 500 if deletion fails
        
    Warning:
        This operation is irreversible
    """
    # Extract per-user Paradigm API key
    api_key = get_paradigm_api_key(raw_request)

    try:
        client = ParadigmClient(api_key=api_key)
        success = await client.delete_file(file_id)
        return {"success": success, "message": f"File {file_id} deleted successfully"}
        
    except Exception as e:
        logger.error(f"Failed to delete file {file_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete file: {str(e)}"
        )

@api_router.get("/files/{file_id}/chunks", tags=["Files"])
async def get_file_chunks(file_id: int, raw_request: Request):
    """
    Get text chunks from an uploaded file for output example extraction.

    Retrieves the parsed text chunks of a previously uploaded file,
    useful for extracting text content from PDFs and documents.

    Args:
        file_id: ID of the file to get chunks from

    Returns:
        dict: File chunks and metadata from Paradigm
    """
    api_key = get_paradigm_api_key(raw_request)

    try:
        client = ParadigmClient(api_key=api_key)
        result = await client.get_file_chunks(file_id)
        return result

    except Exception as e:
        logger.error(f"Failed to get file chunks for {file_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get file chunks: {str(e)}"
        )


@api_router.post("/workflow/generate-package/{workflow_id}", tags=["Workflow Runner"])
async def generate_workflow_package(workflow_id: str):
    """
    Generate a standalone workflow runner package as a ZIP file.

    This endpoint creates a complete, deployable application package containing:
    - Frontend with dynamic UI and PDF generation
    - Backend API server
    - Workflow execution code
    - Paradigm API client
    - Docker configuration
    - Bilingual documentation (FR/EN)

    The generated ZIP can be deployed independently by clients.

    NOTE: This endpoint is disabled on Vercel (production) to stay within
    the 12 Serverless Functions limit. Use it in local development only.

    Args:
        workflow_id: The ID of the workflow to package

    Returns:
        StreamingResponse: ZIP file download

    Raises:
        HTTPException: If workflow not found or generation fails
    """
    # Disable on Vercel to stay within function limit
    if settings.is_vercel:
        raise HTTPException(
            status_code=503,
            detail="Package generation is only available in local development. Please run the Workflow Builder locally to generate packages."
        )

    try:
        from .workflow.generators.workflow_package import WorkflowPackageGenerator, generate_ui_config_simple
        from .workflow.core.analyzer import analyze_workflow_for_ui, generate_simple_description

        logger.info(f"Generating package for workflow: {workflow_id}")

        # Get the workflow from executor
        workflow = workflow_executor.get_workflow(workflow_id)
        if not workflow:
            raise HTTPException(
                status_code=404,
                detail=f"Workflow not found: {workflow_id}"
            )

        # Get the workflow code - either from generated_code or from cells
        workflow_code = workflow.generated_code

        # For cell-based workflows, use the combiner to create clean code
        if not workflow_code:
            plan = workflow_executor.get_workflow_plan(workflow_id)
            if plan and plan.cells:
                # Check if any cells have generated code
                has_code = any(cell.generated_code for cell in plan.cells)
                if has_code:
                    from .workflow.cell.combiner import combine_workflow_cells
                    workflow_code = combine_workflow_cells(
                        plan=plan,
                        workflow_description=workflow.description or ""
                    )
                    logger.info(f"Combined {len(plan.cells)} cells into clean workflow code with parallelism support")

        if not workflow_code:
            raise HTTPException(
                status_code=400,
                detail="Workflow has no generated code. Please ensure the workflow has been executed at least once."
            )

        # Use Claude to analyze workflow code and generate UI config automatically
        logger.info("Analyzing workflow code with Claude to generate UI configuration...")
        try:
            ui_config = await analyze_workflow_for_ui(
                workflow_code=workflow_code,
                workflow_name=workflow.name or "Unnamed Workflow",
                workflow_description=workflow.description or "Generated workflow"
            )
            logger.info(f"UI config generated: {ui_config}")
        except Exception as e:
            logger.error(f"Failed to analyze workflow with Claude: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to analyze workflow code to generate UI configuration. Error: {str(e)}. Please try again or check the workflow code."
            )

        # Generate a simple, user-friendly description (1-3 lines)
        logger.info("Generating simple description...")
        try:
            simple_description = await generate_simple_description(
                workflow_description=workflow.description or "",
                workflow_name=workflow.name or "Unnamed Workflow"
            )
            logger.info(f"Simple description generated: {simple_description}")
        except Exception as e:
            logger.warning(f"Failed to generate simple description: {e}. Using original.")
            simple_description = workflow.description or "Generated workflow"

        # Generate the package
        package_generator = WorkflowPackageGenerator(
            workflow_name=workflow.name or "Unnamed Workflow",
            workflow_description=simple_description,
            workflow_code=workflow_code,
            ui_config=ui_config
        )

        zip_buffer = package_generator.generate_zip()

        # Create filename - sanitize to only allow safe characters in HTTP headers
        raw_name = workflow.name or "workflow"
        workflow_name_slug = re.sub(r'[^a-z0-9]+', '-', raw_name.lower()).strip('-')[:50]
        filename = f"workflow-{workflow_name_slug}-{workflow_id[:8]}.zip"

        logger.info(f"Package generated successfully: {filename}")

        # Return as downloadable ZIP
        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate package: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate package: {str(e)}"
        )


@api_router.post("/workflow/generate-mcp-package/{workflow_id}", tags=["Workflow Runner"])
async def generate_mcp_package(workflow_id: str):
    """
    Generate an MCP (Model Context Protocol) server package as a ZIP file.

    This endpoint creates a complete MCP server package containing:
    - MCP server with tool definitions
    - Workflow execution code
    - Paradigm API client
    - Python package configuration
    - Claude Desktop integration instructions

    The generated package can be used directly in Claude Desktop or any MCP-compatible client.

    NOTE: This endpoint is disabled on Vercel (production) to stay within
    the 12 Serverless Functions limit. Use it in local development only.

    Args:
        workflow_id: The ID of the workflow to package

    Returns:
        StreamingResponse: ZIP file download

    Raises:
        HTTPException: If workflow not found or generation fails
    """
    # Disable on Vercel to stay within function limit
    if settings.is_vercel:
        raise HTTPException(
            status_code=503,
            detail="MCP package generation is only available in local development. Please run the Workflow Builder locally to generate packages."
        )

    try:
        from .workflow.generators.mcp_package import MCPPackageGenerator, extract_workflow_parameters_simple
        from .workflow.core.analyzer import generate_simple_description

        logger.info("Generating MCP package for workflow: {}".format(workflow_id))

        # Get the workflow from executor
        workflow = workflow_executor.get_workflow(workflow_id)
        if not workflow:
            raise HTTPException(
                status_code=404,
                detail="Workflow not found: {}".format(workflow_id)
            )

        # Get the workflow code - either from generated_code or from cells
        workflow_code = workflow.generated_code

        # For cell-based workflows, use the combiner to create clean code
        if not workflow_code:
            plan = workflow_executor.get_workflow_plan(workflow_id)
            if plan and plan.cells:
                # Check if any cells have generated code
                has_code = any(cell.generated_code for cell in plan.cells)
                if has_code:
                    from .workflow.cell.combiner import combine_workflow_cells
                    workflow_code = combine_workflow_cells(
                        plan=plan,
                        workflow_description=workflow.description or ""
                    )
                    logger.info("Combined {} cells into clean workflow code for MCP package".format(len(plan.cells)))

        if not workflow_code:
            raise HTTPException(
                status_code=400,
                detail="Workflow has no generated code. Please ensure the workflow has been executed at least once."
            )

        # Generate a simple, user-friendly description (1-3 lines)
        logger.info("Generating simple description...")
        try:
            simple_description = await generate_simple_description(
                workflow_description=workflow.description or "",
                workflow_name=workflow.name or "Unnamed Workflow"
            )
            logger.info("Simple description generated: {}".format(simple_description))
        except Exception as e:
            logger.warning("Failed to generate simple description: {}. Using original.".format(e))
            simple_description = workflow.description or "Generated workflow"

        # Extract workflow parameters (for now, use simple extraction)
        # Later, we can use Claude to analyze the code and extract parameters automatically
        workflow_parameters = extract_workflow_parameters_simple(workflow.name or "Unnamed Workflow")

        # Define output format description
        workflow_output_format = "JSON object containing the workflow results, including any analysis, extracted data, or generated content."

        # Generate the MCP package
        mcp_generator = MCPPackageGenerator(
            workflow_name=workflow.name or "Unnamed Workflow",
            workflow_description=simple_description,
            workflow_code=workflow_code,
            workflow_parameters=workflow_parameters,
            workflow_output_format=workflow_output_format
        )

        zip_buffer = mcp_generator.generate_zip()

        # Create filename
        raw_name = workflow.name or "workflow"
        workflow_name_slug = re.sub(r'[^a-z0-9]+', '-', raw_name.lower()).strip('-')[:50]
        filename = "mcp-{}-{}.zip".format(workflow_name_slug, workflow_id[:8])

        logger.info("MCP package generated successfully: {}".format(filename))

        # Return as downloadable ZIP
        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={
                "Content-Disposition": "attachment; filename={}".format(filename)
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to generate MCP package: {}".format(str(e)))
        raise HTTPException(
            status_code=500,
            detail="Failed to generate MCP package: {}".format(str(e))
        )


# Include the API router in the main app
app.include_router(api_router, prefix="/api")

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """
    Global exception handler for unhandled errors.
    
    Catches all unhandled exceptions and returns a consistent error response.
    In debug mode, includes detailed error information for troubleshooting.
    In production mode, returns generic error messages to avoid information leakage.
    
    Args:
        request: The HTTP request that caused the exception
        exc: The unhandled exception
        
    Returns:
        ErrorResponse: Standardized error response with timestamp
        
    Note:
        All exceptions are logged for monitoring and debugging purposes
    """
    logger.error(f"Unhandled exception: {str(exc)}")
    return ErrorResponse(
        error="Internal server error",
        details=str(exc) if settings.debug else None,
        timestamp=datetime.utcnow()
    )

# Development server entry point
if __name__ == "__main__":
    import uvicorn
    # Run the development server with auto-reload in debug mode
    uvicorn.run(
        "api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )