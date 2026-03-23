"""Main FastAPI application for the Workflow Automation System."""

import hashlib
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
    ParadigmAgent,
    DiscoveredTool,
    AgentDiscoveryResponse,
)
from .workflow.core.enhancer import WorkflowEnhancer
from .workflow.core.executor import workflow_executor
from .workflow.models import Workflow, WorkflowExecution, ExecutionStatus, WorkflowPlan, WorkflowCell, CellStatus
from .workflow.cell.planner import WorkflowPlanner
from .workflow.cell.executor import CellExecutor
from .paradigm_client import ParadigmClient, paradigm_client

logging.basicConfig(level=logging.INFO if settings.debug else logging.WARNING)
logger = logging.getLogger(__name__)

# Maps workflow_id -> {"cancelled": bool, "started_at": datetime, "status": str}
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


def validate_anthropic_api_key():
    """Validate that Anthropic API key is available, raising 503 if missing."""
    if not settings.anthropic_api_key:
        raise HTTPException(
            status_code=503,
            detail="Anthropic API key not configured. Please set ANTHROPIC_API_KEY environment variable."
        )
    return True

def get_paradigm_api_key(request: Request) -> str:
    """Extract Paradigm API key from header, query param, or server .env fallback."""
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

# ============================================================================
# Tool Discovery Cache
# ============================================================================

# In-memory cache: {api_key_hash: {"data": AgentDiscoveryResponse, "timestamp": float}}
_discovery_cache: Dict[str, Dict[str, Any]] = {}
DISCOVERY_CACHE_TTL = 3600  # 1 hour


def _cache_key(api_key: str) -> str:
    """Generate a short hash key for caching by API key."""
    return hashlib.sha256(api_key.encode()).hexdigest()[:16]


def get_cached_discovery(api_key: str) -> Optional[AgentDiscoveryResponse]:
    """Get cached discovery data for an API key, or None if expired/missing."""
    key = _cache_key(api_key)
    cached = _discovery_cache.get(key)
    if cached and (time.time() - cached["timestamp"]) < DISCOVERY_CACHE_TTL:
        return cached["data"]
    return None


def _get_fallback_tools() -> AgentDiscoveryResponse:
    """Return hardcoded fallback tools when discovery fails."""
    return AgentDiscoveryResponse(
        agents=[],
        native_tools=[
            DiscoveredTool(name="agent_query", type="native",
                          description="AI document queries with multi-turn reasoning"),
            DiscoveredTool(name="get_file_chunks", type="native",
                          description="Raw text extraction from documents"),
            DiscoveredTool(name="wait_for_embedding", type="native",
                          description="Wait for file indexing after upload"),
            DiscoveredTool(name="upload_file", type="native",
                          description="Upload new files to Paradigm"),
        ],
        mcp_tools=[]
    )


app = FastAPI(
    title="Workflow Automation API",
    description="API for creating and executing automated workflows using AI",
    version="1.0.0",
    debug=settings.debug
)

from fastapi import APIRouter
api_router = APIRouter()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "null",  # Allow file:// protocol for local HTML testing
        "http://localhost:3000",  # Local development
        "http://127.0.0.1:3000",
        "https://scaffold-ai-test2.vercel.app",  # Production frontend
        "https://scaffold-ai-test2-milo-rignells-projects.vercel.app",
        "https://scaffold-ai-test2-fi4dvy1xl-milo-rignells-projects.vercel.app",
        "https://scaffold-ai-test2-tawny.vercel.app",
        "https://scaffold-ai-test2-git-main-milo-rignells-projects.vercel.app/",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Paradigm-Api-Key", "Authorization"],
)


@app.get("/", response_class=HTMLResponse, tags=["Frontend"])
async def serve_frontend():
    """Serve the frontend HTML page with no-cache headers."""
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(
            content=content,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    except FileNotFoundError:
        return {
            "message": "Workflow Automation API",
            "version": "1.0.0",
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "note": "Frontend file not found - API only mode"
        }

@app.get("/lighton-logo.png", tags=["Static"])
async def serve_logo():
    """Serve the LightOn logo image."""
    try:
        with open("lighton-logo.png", "rb") as f:
            image_data = f.read()
        return Response(content=image_data, media_type="image/png")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Logo not found")

@app.get("/health", tags=["Health"]) 
async def health_check():
    """Health check endpoint for monitoring."""
    return {
        "message": "Workflow Automation API",
        "version": "1.0.0",
        "status": "healthy", 
        "timestamp": datetime.utcnow().isoformat()
    }

# ============================================================================
# Agent & Tool Discovery Endpoints
# ============================================================================

@api_router.get("/agents/discover", response_model=AgentDiscoveryResponse, tags=["Discovery"])
async def discover_agents_and_tools(raw_request: Request):
    """Discover available Paradigm agents and their tools for the current API key."""
    api_key = get_paradigm_api_key(raw_request)

    # Check cache first
    cached = get_cached_discovery(api_key)
    if cached:
        return cached

    client = ParadigmClient(api_key=api_key)
    try:
        discovery = await client.discover_all()

        # Build response
        agents = []
        all_native_tools = []
        all_mcp_tools = []
        seen_native = set()
        seen_mcp = set()

        for agent_data in discovery.get("agents", []):
            agents.append(ParadigmAgent(
                id=agent_data.get("id", 0),
                name=agent_data.get("name", "Unknown"),
                description=agent_data.get("description"),
                is_default=agent_data.get("is_default", False)
            ))

        # Collect tools from all agents
        for agent_id, tools_data in discovery.get("tools_by_agent", {}).items():
            for tool in tools_data.get("native", []):
                tool_name = tool.get("name", "")
                if tool_name and tool_name not in seen_native:
                    seen_native.add(tool_name)
                    all_native_tools.append(DiscoveredTool(
                        name=tool_name,
                        type="native",
                        description=tool.get("description", ""),
                        require_document=tool.get("require_document"),
                        accepted_file_types=tool.get("accepted_file_types") or []
                    ))

            for mcp_server in tools_data.get("mcp_servers", []):
                server_name = mcp_server.get("name", "")
                if server_name and server_name not in seen_mcp:
                    seen_mcp.add(server_name)
                    all_mcp_tools.append(DiscoveredTool(
                        name=server_name,
                        type="mcp",
                        description=mcp_server.get("description", ""),
                        mcp_server_name=server_name
                    ))

        response = AgentDiscoveryResponse(
            agents=agents,
            native_tools=all_native_tools,
            mcp_tools=all_mcp_tools
        )

        # Cache the result
        _discovery_cache[_cache_key(api_key)] = {
            "data": response,
            "timestamp": time.time()
        }

        return response

    except Exception as e:
        logger.error("Agent discovery failed: {}".format(str(e)))
        return _get_fallback_tools()
    finally:
        await client.close()


@api_router.get("/agents/{agent_id}/tools", tags=["Discovery"])
async def get_agent_tools(agent_id: int, raw_request: Request):
    """Get the tools available to a specific Paradigm agent."""
    api_key = get_paradigm_api_key(raw_request)

    client = ParadigmClient(api_key=api_key)
    try:
        tools_data = await client.get_agent_tools(agent_id)

        native_tools = [
            DiscoveredTool(
                name=t.get("name", ""),
                type="native",
                description=t.get("description", ""),
                require_document=t.get("require_document"),
                accepted_file_types=t.get("accepted_file_types") or []
            )
            for t in tools_data.get("native", [])
        ]

        mcp_tools = [
            DiscoveredTool(
                name=s.get("name", ""),
                type="mcp",
                description=s.get("description", ""),
                mcp_server_name=s.get("name", "")
            )
            for s in tools_data.get("mcp_servers", [])
        ]

        return {"native_tools": native_tools, "mcp_tools": mcp_tools}

    except Exception as e:
        logger.error("Agent tools fetch failed: {}".format(str(e)))
        raise HTTPException(status_code=500, detail="Failed to fetch agent tools: {}".format(str(e)))
    finally:
        await client.close()


# ============================================================================
# Workflow Endpoints
# ============================================================================

@api_router.post("/workflows/enhance-description", response_model=WorkflowDescriptionEnhanceResponse, tags=["Workflows"])
async def enhance_workflow_description(request: WorkflowDescriptionEnhanceRequest, raw_request: Request):
    """Enhance a raw workflow description into a detailed specification using Claude."""
    validate_anthropic_api_key()

    try:
        logger.info("Enhancing workflow description: {}...".format(request.description[:100]))

        # Get discovered tools for the enhancer (if available)
        available_tools = None
        try:
            api_key = get_paradigm_api_key(raw_request)
            available_tools = get_cached_discovery(api_key)
        except Exception:
            pass

        from .clients import create_anthropic_client
        enhancer = WorkflowEnhancer(create_anthropic_client())
        result = await enhancer.enhance_workflow_description(
            request.description,
            output_example=request.output_example,
            available_tools=available_tools
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

@api_router.post("/workflows-cell-based", response_model=CellBasedWorkflowResponse, tags=["Cell-Based Workflows"])
async def create_cell_based_workflow(request: WorkflowCreateRequest, raw_request: Request):
    """Create a new cell-based workflow with a step-by-step execution plan."""
    validate_anthropic_api_key()

    try:
        logger.info("Creating cell-based workflow: {}...".format(request.description[:100]))

        # Get discovered tools for the planner (if available)
        available_tools = None
        try:
            api_key = get_paradigm_api_key(raw_request)
            cached = get_cached_discovery(api_key)
            if cached:
                available_tools = cached
        except Exception:
            pass  # No API key or no cache — planner will use hardcoded tools

        planner = WorkflowPlanner()
        plan = await planner.create_plan(
            description=request.description,
            context=request.context,
            output_example=request.output_example,
            available_tools=available_tools
        )

        # Store output_example in context for later use in evaluation
        workflow_context = request.context or {}
        if request.output_example:
            workflow_context["output_example"] = request.output_example

        workflow_name = request.name
        if not workflow_name:
            desc = request.description.strip()
            for sep in ['.', '\n', '!']:
                first_sentence = desc.split(sep)[0].strip()
                if len(first_sentence) < len(desc):
                    desc = first_sentence
                    break
            workflow_name = desc[:60].rstrip(' .,;:!-')

        workflow = Workflow(
            name=workflow_name,
            description=request.description,
            status="ready",
            context=workflow_context
        )

        plan.workflow_id = workflow.id
        for cell in plan.cells:
            cell.workflow_id = workflow.id

        workflow_executor.store_workflow(workflow)
        workflow_executor.store_workflow_plan(workflow.id, plan)

        logger.info("Cell-based workflow created: {} with {} cells".format(
            workflow.id, len(plan.cells)
        ))

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
                output_variables=cell.output_variables,
                execution_time=cell.execution_time,
                error=cell.error,
                evaluation_score=cell.evaluation_score,
                evaluation_attempts=cell.evaluation_attempts
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
    """Execute a cell-based workflow with real-time SSE streaming of results."""
    validate_anthropic_api_key()
    api_key = get_paradigm_api_key(raw_request)

    async def event_generator():
        try:
            workflow = workflow_executor.get_workflow(workflow_id)
            if not workflow:
                yield "data: {}\n\n".format(json.dumps({
                    "type": "error",
                    "error": "Workflow not found: {}".format(workflow_id)
                }))
                return

            plan = workflow_executor.get_workflow_plan(workflow_id)
            if not plan:
                yield "data: {}\n\n".format(json.dumps({
                    "type": "error",
                    "error": "Workflow plan not found. This may be a monolithic workflow."
                }))
                return

            is_parallel = plan.is_parallel_workflow()

            logger.info("Starting {} execution for workflow: {} ({} layers, {} cells)".format(
                "PARALLEL" if is_parallel else "sequential",
                workflow_id,
                plan.get_max_layer(),
                len(plan.cells)
            ))

            # Pass agent_id and discovered tools to executor
            agent_id = raw_request.query_params.get("agent_id") or raw_request.headers.get("X-Paradigm-Agent-Id")
            cached_tools = get_cached_discovery(api_key)
            executor = CellExecutor(
                paradigm_api_key=api_key,
                agent_id=int(agent_id) if agent_id else None,
                available_tools=cached_tools
            )

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
    """Execute a cell-based workflow with layer-based parallelization via SSE."""
    validate_anthropic_api_key()
    api_key = get_paradigm_api_key(raw_request)

    async def event_generator():
        try:
            workflow = workflow_executor.get_workflow(workflow_id)
            if not workflow:
                yield "data: {}\n\n".format(json.dumps({
                    "type": "error",
                    "error": "Workflow not found: {}".format(workflow_id)
                }))
                return

            plan = workflow_executor.get_workflow_plan(workflow_id)
            if not plan:
                yield "data: {}\n\n".format(json.dumps({
                    "type": "error",
                    "error": "Workflow plan not found. This may be a monolithic workflow."
                }))
                return

            is_parallel = plan.is_parallel_workflow()

            logger.info("Starting {} execution for workflow: {} ({} layers, {} cells)".format(
                "parallel" if is_parallel else "sequential",
                workflow_id,
                plan.get_max_layer(),
                len(plan.cells)
            ))

            # Pass agent_id and discovered tools to executor
            agent_id = raw_request.query_params.get("agent_id") or raw_request.headers.get("X-Paradigm-Agent-Id")
            cached_tools = get_cached_discovery(api_key)
            executor = CellExecutor(
                paradigm_api_key=api_key,
                agent_id=int(agent_id) if agent_id else None,
                available_tools=cached_tools
            )

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
    """Execute a workflow with LLM-as-judge evaluation using smoke test + retry approach."""
    validate_anthropic_api_key()
    api_key = get_paradigm_api_key(raw_request)

    async def event_generator():
        try:
            workflow = workflow_executor.get_workflow(workflow_id)
            if not workflow:
                yield "data: {}\n\n".format(json.dumps({
                    "type": "error",
                    "error": "Workflow not found: {}".format(workflow_id)
                }))
                return

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

            mark_execution_started(workflow_id)

            examples = [
                {
                    "id": example.id or "example_{}".format(i),
                    "user_input": example.user_input,
                    "attached_file_ids": example.attached_file_ids or []
                }
                for i, example in enumerate(request.examples)
            ]

            # Pass agent_id and discovered tools to executor
            agent_id = raw_request.query_params.get("agent_id") or raw_request.headers.get("X-Paradigm-Agent-Id")
            cached_tools = get_cached_discovery(api_key)
            executor = CellExecutor(
                paradigm_api_key=api_key,
                agent_id=int(agent_id) if agent_id else None,
                available_tools=cached_tools
            )
            async for event in executor.execute_workflow_with_evaluation(
                plan=plan,
                examples=examples,
                workflow_description=workflow.description
            ):
                if is_execution_cancelled(workflow_id):
                    yield "data: {}\n\n".format(json.dumps({
                        "type": "workflow_stopped",
                        "message": "Execution stopped by user",
                        "timestamp": datetime.utcnow().isoformat()
                    }))
                    mark_execution_completed(workflow_id)
                    return

                yield "data: {}\n\n".format(json.dumps(event))

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
    """Stop an in-progress workflow execution after the current cell completes."""
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
    """Get the current execution status of a workflow."""
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
    """Retrieve the execution plan for a cell-based workflow."""
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
                output_variables=cell.output_variables,
                execution_time=cell.execution_time,
                error=cell.error,
                evaluation_score=cell.evaluation_score,
                evaluation_attempts=cell.evaluation_attempts
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
    """Acknowledge approval of a cell's output."""
    try:
        logger.info("Cell approved by user: {} in workflow {}".format(cell_id, workflow_id))

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
    """Rerun a specific cell with its current code and the latest execution context."""
    api_key = get_paradigm_api_key(raw_request)

    try:
        logger.info("Rerunning cell {} in workflow {}".format(cell_id, workflow_id))

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

        execution_context = workflow_executor.get_execution_context(workflow_id)

        if not execution_context:
            execution_context = {
                "user_input": "",
                "attached_file_ids": []
            }
            logger.warning("No execution context found, using empty context")

        agent_id = raw_request.query_params.get("agent_id") or raw_request.headers.get("X-Paradigm-Agent-Id")
        cached_tools = get_cached_discovery(api_key)
        executor = CellExecutor(
            paradigm_api_key=api_key,
            agent_id=int(agent_id) if agent_id else None,
            available_tools=cached_tools
        )

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

            output_variables = cell_result.get("variables", {})
            output_text = cell_result.get("output", "")

            execution_context.update(output_variables)
            workflow_executor.store_execution_context(workflow_id, execution_context)

            formatted_outputs = executor._format_output_variables(output_variables)

            cell.mark_completed(
                output=output_text,
                variables=output_variables,
                execution_time=0
            )
            workflow_executor.store_workflow_plan(workflow_id, plan)

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
    """Execute a single cell with provided input and context."""
    validate_anthropic_api_key()
    api_key = get_paradigm_api_key(raw_request)

    try:
        logger.info("Executing single cell {} in workflow {} with input: {}".format(
            cell_id, workflow_id, request.user_input[:50] if request.user_input else "(empty)"
        ))

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

        context = {
            "user_input": request.user_input,
            "attached_file_ids": request.attached_file_ids or []
        }

        if request.execution_context:
            context.update(request.execution_context)

        agent_id = raw_request.query_params.get("agent_id") or raw_request.headers.get("X-Paradigm-Agent-Id")
        cached_tools = get_cached_discovery(api_key)
        executor = CellExecutor(
            paradigm_api_key=api_key,
            agent_id=int(agent_id) if agent_id else None,
            available_tools=cached_tools
        )

        if not cell.generated_code:
            logger.info("Cell {} has no generated code, generating now...".format(cell_id))
            try:
                description, code = await executor.cell_generator.generate_cell_code(
                    cell=cell,
                    available_context=plan.shared_context_schema or {},
                    workflow_description=workflow.description
                )
                cell.mark_ready(code, description)
                workflow_executor.store_workflow_plan(workflow_id, plan)
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

            output_variables = cell_result.get("variables", {})
            output_text = cell_result.get("output", "")

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
    """Regenerate a cell's code incorporating user feedback."""
    try:
        feedback = request.feedback.strip()

        logger.info("Received feedback for cell {} in workflow {}: {}".format(
            cell_id, workflow_id, feedback[:100]
        ))

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

        api_key = get_paradigm_api_key(raw_request)
        agent_id = raw_request.query_params.get("agent_id") or raw_request.headers.get("X-Paradigm-Agent-Id")
        cached_tools = get_cached_discovery(api_key)
        executor = CellExecutor(
            paradigm_api_key=api_key,
            agent_id=int(agent_id) if agent_id else None,
            available_tools=cached_tools
        )

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

        cell.generated_code = new_code
        cell.status = CellStatus.READY
        workflow_executor.store_workflow_plan(workflow_id, plan)

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
    """Update a cell's success criteria and reset it and dependents for re-execution."""
    try:
        logger.info("Updating success criteria for cell {} in workflow {}".format(cell_id, workflow_id))

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

        cell.success_criteria = request.success_criteria

        # Reset cell and dependents: keep code, clear execution results
        cell.status = CellStatus.READY
        cell.output = None
        cell.output_variables = None
        cell.error = None

        for dep_cell in plan.cells:
            if cell_id in dep_cell.depends_on or dep_cell.layer > cell.layer:
                dep_cell.status = CellStatus.READY
                dep_cell.output = None
                dep_cell.output_variables = None
                dep_cell.error = None

        workflow_executor.store_workflow_plan(workflow_id, plan)

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


@api_router.post("/files/upload", response_model=FileUploadResponse, tags=["Files"])
async def upload_file(
    raw_request: Request,
    file: UploadFile = File(...)
):
    """Upload a file to Paradigm and wait for embedding to complete."""
    api_key = get_paradigm_api_key(raw_request)

    try:
        logger.info(f"Uploading file: {file.filename}")

        # Read file and enforce size limit (200MB) to prevent OOM
        file_content = await file.read()
        MAX_FILE_SIZE = 200 * 1024 * 1024  # 200MB
        if len(file_content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail="File too large. Maximum size is 200MB."
            )

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
    """Retrieve metadata and optionally content of an uploaded file."""
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
    """Permanently delete an uploaded file from Paradigm."""
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
    """Get parsed text chunks from an uploaded file."""
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
    """Generate a standalone deployable workflow runner package as a ZIP file."""
    # Disabled on Vercel to stay within 12 Serverless Functions limit
    if settings.is_vercel:
        raise HTTPException(
            status_code=503,
            detail="Package generation is only available in local development. Please run the Workflow Builder locally to generate packages."
        )

    try:
        from .workflow.generators.workflow_package import WorkflowPackageGenerator, generate_ui_config_simple
        from .workflow.core.analyzer import analyze_workflow_for_ui, generate_simple_description

        logger.info(f"Generating package for workflow: {workflow_id}")

        workflow = workflow_executor.get_workflow(workflow_id)
        if not workflow:
            raise HTTPException(
                status_code=404,
                detail=f"Workflow not found: {workflow_id}"
            )

        workflow_code = workflow.generated_code

        # For cell-based workflows, combine cell code into a single module
        if not workflow_code:
            plan = workflow_executor.get_workflow_plan(workflow_id)
            if plan and plan.cells:
                has_code = any(cell.generated_code for cell in plan.cells)
                if has_code:
                    from .workflow.cell.combiner import combine_workflow_cells
                    workflow_code = combine_workflow_cells(
                        plan=plan,
                        workflow_description=workflow.description or ""
                    )
                    logger.info(f"Combined {len(plan.cells)} cells into clean workflow code")

        if not workflow_code:
            raise HTTPException(
                status_code=400,
                detail="Workflow has no generated code. Please ensure the workflow has been executed at least once."
            )

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

        package_generator = WorkflowPackageGenerator(
            workflow_name=workflow.name or "Unnamed Workflow",
            workflow_description=simple_description,
            workflow_code=workflow_code,
            ui_config=ui_config
        )

        zip_buffer = package_generator.generate_zip()

        raw_name = workflow.name or "workflow"
        workflow_name_slug = re.sub(r'[^a-z0-9]+', '-', raw_name.lower()).strip('-')[:50]
        filename = f"workflow-{workflow_name_slug}-{workflow_id[:8]}.zip"

        logger.info(f"Package generated successfully: {filename}")

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
    """Generate an MCP server package as a ZIP file for Claude Desktop integration."""
    # Disabled on Vercel to stay within 12 Serverless Functions limit
    if settings.is_vercel:
        raise HTTPException(
            status_code=503,
            detail="MCP package generation is only available in local development. Please run the Workflow Builder locally to generate packages."
        )

    try:
        from .workflow.generators.mcp_package import MCPPackageGenerator, extract_workflow_parameters_simple
        from .workflow.core.analyzer import generate_simple_description

        logger.info("Generating MCP package for workflow: {}".format(workflow_id))

        workflow = workflow_executor.get_workflow(workflow_id)
        if not workflow:
            raise HTTPException(
                status_code=404,
                detail="Workflow not found: {}".format(workflow_id)
            )

        workflow_code = workflow.generated_code

        # For cell-based workflows, combine cell code into a single module
        if not workflow_code:
            plan = workflow_executor.get_workflow_plan(workflow_id)
            if plan and plan.cells:
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

        workflow_parameters = extract_workflow_parameters_simple(workflow.name or "Unnamed Workflow")
        workflow_output_format = "JSON object containing the workflow results, including any analysis, extracted data, or generated content."

        mcp_generator = MCPPackageGenerator(
            workflow_name=workflow.name or "Unnamed Workflow",
            workflow_description=simple_description,
            workflow_code=workflow_code,
            workflow_parameters=workflow_parameters,
            workflow_output_format=workflow_output_format
        )

        zip_buffer = mcp_generator.generate_zip()

        raw_name = workflow.name or "workflow"
        workflow_name_slug = re.sub(r'[^a-z0-9]+', '-', raw_name.lower()).strip('-')[:50]
        filename = "mcp-{}-{}.zip".format(workflow_name_slug, workflow_id[:8])

        logger.info("MCP package generated successfully: {}".format(filename))

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


app.include_router(api_router, prefix="/api")

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Return a consistent error response for unhandled exceptions."""
    logger.error(f"Unhandled exception: {str(exc)}")
    return ErrorResponse(
        error="Internal server error",
        details=str(exc) if settings.debug else None,
        timestamp=datetime.utcnow()
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )