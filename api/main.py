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
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response, StreamingResponse
import uvicorn

from .config import settings
from .pdf_generator import pdf_generator
from .models import (
    WorkflowCreateRequest,
    WorkflowExecuteRequest,
    WorkflowResponse,
    WorkflowExecutionResponse,
    ErrorResponse,
    FileUploadResponse,
    FileInfoResponse,
    WorkflowWithFilesRequest,
    WorkflowDescriptionEnhanceRequest,
    WorkflowDescriptionEnhanceResponse,
)
from .workflow.generator import workflow_generator
from .workflow.executor import workflow_executor
from .workflow.models import Workflow, WorkflowExecution
from .api_clients import paradigm_client  # Updated import

# Configure logging based on debug settings
logging.basicConfig(level=logging.INFO if settings.debug else logging.WARNING)
logger = logging.getLogger(__name__)

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

def validate_lighton_api_key():
    """
    Validate that LightOn API key is available.
    
    Returns:
        bool: True if API key is available
        
    Raises:
        HTTPException: 503 if API key is missing
    """
    if not settings.lighton_api_key:
        raise HTTPException(
            status_code=503,
            detail="LightOn API key not configured. Please set LIGHTON_API_KEY environment variable."
        )
    return True

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
    """
    try:
        # Try to read the index.html file from the project root
        with open("index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
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
        logger.info(f"Enhancing workflow description: {request.description[:100]}...")
        
        # Enhance the description
        result = await workflow_generator.enhance_workflow_description(request.description)
        
        logger.info("Workflow description enhanced successfully")
        
        return WorkflowDescriptionEnhanceResponse(
            enhanced_description=result["enhanced_description"],
            questions=result["questions"],
            warnings=result["warnings"]
        )
        
    except Exception as e:
        logger.error(f"Failed to enhance workflow description: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to enhance workflow description: {str(e)}"
        )

@api_router.post("/workflows", response_model=WorkflowResponse, tags=["Workflows"])
async def create_workflow(request: WorkflowCreateRequest):
    """
    Create a new workflow from a natural language description.
    
    This endpoint uses AI to generate executable Python code from a natural
    language workflow description. The generated code integrates with both
    Anthropic and LightOn Paradigm APIs for document processing and analysis.
    
    Args:
        request: Workflow creation request containing description, optional name, and context
        
    Returns:
        WorkflowResponse: Complete workflow details including generated code
        
    Raises:
        HTTPException: 503 if API keys are missing, 500 if workflow generation fails
        
    Example:
        POST /workflows
        {
            \"description\": \"Search documents about AI, then analyze findings\",
            \"name\": \"AI Research Workflow\"
        }
    """
    # Validate required API keys
    validate_anthropic_api_key()
    
    try:
        logger.info(f"Creating workflow: {request.description[:100]}...")
        
        # Generate the workflow
        workflow = await workflow_generator.generate_workflow(
            description=request.description,
            name=request.name,
            context=request.context
        )
        
        # Store the workflow in the executor
        workflow_executor.store_workflow(workflow)
        
        logger.info(f"Workflow created successfully: {workflow.id}")
        
        return WorkflowResponse(
            id=workflow.id,
            name=workflow.name,
            description=workflow.description,
            status=workflow.status,
            generated_code=workflow.generated_code,
            created_at=workflow.created_at,
            updated_at=workflow.updated_at,
            error=workflow.error
        )
        
    except Exception as e:
        logger.error(f"Failed to create workflow: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create workflow: {str(e)}"
        )

@api_router.get("/workflows/{workflow_id}", response_model=WorkflowResponse, tags=["Workflows"])
async def get_workflow(workflow_id: str):
    """
    Retrieve details of a specific workflow by ID.
    
    Returns complete workflow information including generated code,
    current status, and metadata. Used to check workflow status
    and retrieve generated code for inspection.
    
    Args:
        workflow_id: Unique identifier of the workflow to retrieve
        
    Returns:
        WorkflowResponse: Complete workflow details
        
    Raises:
        HTTPException: 404 if workflow not found, 500 for other errors
    """
    try:
        workflow = workflow_executor.get_workflow(workflow_id)
        if not workflow:
            raise HTTPException(
                status_code=404,
                detail=f"Workflow {workflow_id} not found"
            )
        
        return WorkflowResponse(
            id=workflow.id,
            name=workflow.name,
            description=workflow.description,
            status=workflow.status,
            generated_code=workflow.generated_code,
            created_at=workflow.created_at,
            updated_at=workflow.updated_at,
            error=workflow.error
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get workflow {workflow_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get workflow: {str(e)}"
        )

@api_router.post("/workflows/{workflow_id}/execute", response_model=WorkflowExecutionResponse, tags=["Execution"])
async def execute_workflow(workflow_id: str, request: WorkflowExecuteRequest):
    """
    Execute a workflow with user input and optional file attachments.

    Runs the generated workflow code with the provided user input.
    Supports file attachments that can be processed within the workflow.
    Execution is performed in a secure, isolated environment with timeout protection.

    Args:
        workflow_id: ID of the workflow to execute
        request: Execution request with user input and optional file IDs

    Returns:
        WorkflowExecutionResponse: Execution results with status and timing

    Raises:
        HTTPException: 400 for validation errors, 500 for execution failures

    Note:
        Execution timeout is configured via settings.max_execution_time (default: 5 minutes)
    """
    try:
        logger.info(f"Executing workflow {workflow_id} with input: {request.user_input[:100]}...")

        # If files are attached, verify they are fully indexed before executing
        if request.attached_file_ids:
            logger.info(f"🔍 Verifying {len(request.attached_file_ids)} attached files are ready for analysis...")
            validate_lighton_api_key()

            max_wait_time = 60  # Maximum 60 seconds wait
            poll_interval = 3  # Check every 3 seconds
            elapsed_time = 0

            while elapsed_time < max_wait_time:
                all_ready = True
                files_status = []

                for file_id in request.attached_file_ids:
                    try:
                        file_info = await paradigm_client.get_file_info(file_id)
                        status = file_info.get("status", "unknown")
                        files_status.append(f"File {file_id}: {status}")

                        # Check if file is ready (status should be "embedded" or similar)
                        if status.lower() not in ["completed", "complete", "indexed", "ready", "success", "embedded"]:
                            all_ready = False
                            logger.info(f"⏳ File {file_id} not ready yet (status: {status})")
                    except Exception as e:
                        logger.error(f"❌ Failed to check file {file_id} status: {str(e)}")
                        all_ready = False

                if all_ready:
                    logger.info(f"✅ All {len(request.attached_file_ids)} files are ready for analysis!")
                    break

                # Wait before next check
                await asyncio.sleep(poll_interval)
                elapsed_time += poll_interval
                logger.info(f"⏳ Waiting for files to be indexed... ({elapsed_time}s / {max_wait_time}s)")

            if not all_ready:
                logger.warning(f"⚠️ Files not fully indexed after {max_wait_time}s, proceeding anyway...")
                logger.warning(f"📋 Files status: {', '.join(files_status)}")

        # Execute the workflow
        execution = await workflow_executor.execute_workflow(workflow_id, request.user_input, request.attached_file_ids)

        logger.info(f"Workflow execution completed: {execution.id} (status: {execution.status})")

        return WorkflowExecutionResponse(
            workflow_id=execution.workflow_id,
            execution_id=execution.id,
            result=execution.result,
            status=execution.status.value,
            execution_time=execution.execution_time,
            error=execution.error,
            created_at=execution.created_at
        )

    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to execute workflow {workflow_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to execute workflow: {str(e)}"
        )

@api_router.get("/workflows/{workflow_id}/executions/{execution_id}", response_model=WorkflowExecutionResponse, tags=["Execution"])
async def get_execution(workflow_id: str, execution_id: str):
    """
    Retrieve details of a specific workflow execution.
    
    Returns execution results, status, timing information, and any errors
    that occurred during execution. Used for monitoring and debugging
    workflow executions.
    
    Args:
        workflow_id: ID of the parent workflow
        execution_id: Unique identifier of the execution to retrieve
        
    Returns:
        WorkflowExecutionResponse: Complete execution details
        
    Raises:
        HTTPException: 404 if execution not found, 400 if execution doesn't belong to workflow
    """
    try:
        execution = workflow_executor.get_execution(execution_id)
        if not execution:
            raise HTTPException(
                status_code=404,
                detail=f"Execution {execution_id} not found"
            )
        
        if execution.workflow_id != workflow_id:
            raise HTTPException(
                status_code=400,
                detail=f"Execution {execution_id} does not belong to workflow {workflow_id}"
            )
        
        return WorkflowExecutionResponse(
            workflow_id=execution.workflow_id,
            execution_id=execution.id,
            result=execution.result,
            status=execution.status.value,
            execution_time=execution.execution_time,
            error=execution.error,
            created_at=execution.created_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get execution {execution_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get execution: {str(e)}"
        )

@api_router.get("/workflows/{workflow_id}/executions/{execution_id}/pdf", tags=["Execution"])
async def get_execution_pdf(workflow_id: str, execution_id: str):
    """
    Generate and download a PDF report for a workflow execution.

    Creates a professional PDF document containing the workflow execution
    results, status, timing information, and metadata. The PDF is suitable
    for sharing with clients and includes no vendor branding.

    Args:
        workflow_id: ID of the parent workflow
        execution_id: Unique identifier of the execution

    Returns:
        StreamingResponse: PDF file download with application/pdf content type

    Raises:
        HTTPException: 404 if workflow or execution not found,
                      400 if execution doesn't belong to workflow,
                      500 if PDF generation fails

    Example:
        GET /api/workflows/abc123/executions/def456/pdf

        Downloads a file named: workflow_execution_report_abc123_def456.pdf
    """
    try:
        # Get workflow details
        workflow = workflow_executor.get_workflow(workflow_id)
        if not workflow:
            raise HTTPException(
                status_code=404,
                detail=f"Workflow {workflow_id} not found"
            )

        # Get execution details
        execution = workflow_executor.get_execution(execution_id)
        if not execution:
            raise HTTPException(
                status_code=404,
                detail=f"Execution {execution_id} not found"
            )

        # Verify execution belongs to workflow
        if execution.workflow_id != workflow_id:
            raise HTTPException(
                status_code=400,
                detail=f"Execution {execution_id} does not belong to workflow {workflow_id}"
            )

        logger.info(f"Generating PDF report for workflow {workflow_id}, execution {execution_id}")

        # Generate PDF
        pdf_buffer = pdf_generator.generate_report(
            workflow_name=workflow.name or "Unnamed Workflow",
            workflow_description=workflow.description,
            execution_result=execution.result or "No result available",
            execution_status=execution.status.value,
            execution_time=execution.execution_time,
            execution_date=execution.created_at,
            workflow_id=workflow_id,
            execution_id=execution_id
        )

        # Create filename
        filename = f"workflow_execution_report_{workflow_id}_{execution_id}.pdf"

        logger.info(f"PDF report generated successfully: {filename}")

        # Return PDF as streaming response
        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate PDF for execution {execution_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate PDF report: {str(e)}"
        )

# File upload and management endpoints

@api_router.post("/files/upload", response_model=FileUploadResponse, tags=["Files"])
async def upload_file(
    file: UploadFile = File(...),
    collection_type: str = Form("private"),
    workspace_id: Optional[int] = Form(None)
):
    """
    Upload a file to Paradigm for document processing and analysis.
    
    Files are automatically processed, indexed, and made available for use
    in workflows. Supports various document formats and collection types
    for organizing files within different scopes.
    
    Args:
        file: The file to upload (multipart/form-data)
        collection_type: Collection scope - 'private', 'company', or 'workspace'
        workspace_id: Required if collection_type is 'workspace'
        
    Returns:
        FileUploadResponse: File metadata including ID, size, and processing status
        
    Raises:
        HTTPException: 503 if API keys are missing, 500 if upload fails
        
    Note:
        Files are processed asynchronously and may take time to become fully searchable
    """
    # Validate required API keys
    validate_lighton_api_key()
    
    try:
        logger.info(f"Uploading file: {file.filename}")
        
        # Read file content
        file_content = await file.read()
        
        # Upload to Paradigm
        result = await paradigm_client.upload_file(
            file_content=file_content,
            filename=file.filename,
            collection_type=collection_type,
            workspace_id=workspace_id
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
async def get_file_info(file_id: int, include_content: bool = False):
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
    # Validate required API keys
    validate_lighton_api_key()
    
    try:
        result = await paradigm_client.get_file_info(file_id, include_content)
        return FileInfoResponse(**result)
        
    except Exception as e:
        logger.error(f"Failed to get file info for {file_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get file info: {str(e)}"
        )

@api_router.delete("/files/{file_id}", tags=["Files"])
async def delete_file(file_id: int):
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
    # Validate required API keys
    validate_lighton_api_key()
    
    try:
        success = await paradigm_client.delete_file(file_id)
        return {"success": success, "message": f"File {file_id} deleted successfully"}
        
    except Exception as e:
        logger.error(f"Failed to delete file {file_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete file: {str(e)}"
        )

@api_router.post("/workflows-with-files", response_model=WorkflowResponse, tags=["Workflows"])
async def create_workflow_with_files(request: WorkflowWithFilesRequest):
    """
    Create a workflow that has access to specific uploaded files.
    
    Generates workflow code that can process and analyze the specified
    uploaded files. The file IDs are embedded in the workflow context
    so the generated code can reference them directly.
    
    Args:
        request: Workflow creation request with file IDs to attach
        
    Returns:
        WorkflowResponse: Complete workflow details with file access capabilities
        
    Raises:
        HTTPException: 503 if API keys are missing, 500 if workflow generation fails
        
    Note:
        Generated workflow will have access to global 'attached_file_ids' variable
    """
    # Validate required API keys
    validate_anthropic_api_key()
    
    try:
        logger.info(f"Creating workflow with files: {request.uploaded_file_ids}")
        
        # Add file IDs to context
        context = request.context or {}
        if request.uploaded_file_ids:
            context["uploaded_file_ids"] = request.uploaded_file_ids
            context["use_uploaded_files"] = True
        
        # Generate the workflow
        workflow = await workflow_generator.generate_workflow(
            description=request.description,
            name=request.name,
            context=context
        )
        
        # Store the workflow in the executor
        workflow_executor.store_workflow(workflow)
        
        logger.info(f"Workflow with files created successfully: {workflow.id}")
        
        return WorkflowResponse(
            id=workflow.id,
            name=workflow.name,
            description=workflow.description,
            status=workflow.status,
            generated_code=workflow.generated_code,
            created_at=workflow.created_at,
            updated_at=workflow.updated_at,
            error=workflow.error
        )
        
    except Exception as e:
        logger.error(f"Failed to create workflow with files: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create workflow with files: {str(e)}"
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
        from .workflow.package_generator import WorkflowPackageGenerator, generate_ui_config_simple
        from .workflow.workflow_analyzer import analyze_workflow_for_ui, generate_simple_description

        logger.info(f"Generating package for workflow: {workflow_id}")

        # Get the workflow from executor
        workflow = workflow_executor.get_workflow(workflow_id)
        if not workflow:
            raise HTTPException(
                status_code=404,
                detail=f"Workflow not found: {workflow_id}"
            )

        # Use Claude to analyze workflow code and generate UI config automatically
        logger.info("Analyzing workflow code with Claude to generate UI configuration...")
        try:
            ui_config = await analyze_workflow_for_ui(
                workflow_code=workflow.generated_code,
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
            workflow_code=workflow.generated_code,
            ui_config=ui_config
        )

        zip_buffer = package_generator.generate_zip()

        # Create filename
        workflow_name_slug = (workflow.name or "workflow").lower().replace(' ', '-')
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
        from .workflow.mcp_package_generator import MCPPackageGenerator, extract_workflow_parameters_simple
        from .workflow.workflow_analyzer import generate_simple_description

        logger.info("Generating MCP package for workflow: {}".format(workflow_id))

        # Get the workflow from executor
        workflow = workflow_executor.get_workflow(workflow_id)
        if not workflow:
            raise HTTPException(
                status_code=404,
                detail="Workflow not found: {}".format(workflow_id)
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
            workflow_code=workflow.generated_code,
            workflow_parameters=workflow_parameters,
            workflow_output_format=workflow_output_format
        )

        zip_buffer = mcp_generator.generate_zip()

        # Create filename
        workflow_name_slug = (workflow.name or "workflow").lower().replace(' ', '-').replace('_', '-')
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