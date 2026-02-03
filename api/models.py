"""
Pydantic Models for API Request/Response Schemas

This module defines all the data models used for API request and response schemas.
It includes models for workflows, executions, file operations, and error handling.

Key Models:
    - WorkflowCreateRequest: For creating new workflows
    - WorkflowExecuteRequest: For executing workflows with user input
    - WorkflowResponse: Standard workflow response format
    - WorkflowExecutionResponse: Execution result format
    - File-related models: For file upload/management operations
    - Error models: Standard error response format

Features:
    - Pydantic validation and serialization
    - Type hints and field descriptions
    - Enum-based status management
    - DateTime handling with proper formatting
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from enum import Enum

class WorkflowStatus(str, Enum):
    """
    Enumeration of possible workflow status values.
    
    States:
        CREATED: Workflow has been created but code generation hasn't started
        GENERATING: AI is currently generating code for the workflow
        READY: Code generation complete, workflow ready for execution
        EXECUTING: Workflow is currently being executed
        COMPLETED: Workflow execution completed successfully
        FAILED: Workflow creation or execution failed
    """
    CREATED = "created"
    GENERATING = "generating"
    READY = "ready"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"

class WorkflowCreateRequest(BaseModel):
    """
    Request model for creating a new workflow.

    Used when users want to create a workflow from a natural language description.
    The system will generate executable code based on the description and context.
    """
    description: str = Field(
        ...,
        description="Natural language description of the workflow",
        min_length=10,
        max_length=50000
    )
    name: Optional[str] = Field(None, description="Optional name for the workflow")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context for code generation")

class WorkflowExecuteRequest(BaseModel):
    """
    Request model for executing an existing workflow.

    Contains the user input to process and optional file attachments.
    The workflow will be executed with this input and return results.
    """
    user_input: str = Field(
        ...,
        description="Input data to process through the workflow",
        min_length=1,
        max_length=10000
    )
    attached_file_ids: Optional[List[int]] = Field(
        None,
        description="List of file IDs attached to this query",
        max_length=20
    )

class WorkflowResponse(BaseModel):
    """
    Standard response model for workflow operations.
    
    Contains all workflow metadata including generated code, status, and timing.
    Used for both creation and retrieval endpoints.
    """
    id: str = Field(..., description="Unique workflow identifier")
    name: Optional[str] = Field(None, description="Workflow name")
    description: str = Field(..., description="Workflow description")
    status: WorkflowStatus = Field(..., description="Current workflow status")
    generated_code: Optional[str] = Field(None, description="Generated Python code")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    error: Optional[str] = Field(None, description="Error message if failed")

class WorkflowExecutionResponse(BaseModel):
    """
    Response model for workflow execution operations.
    
    Contains execution results, status, timing, and any errors that occurred.
    Tracks individual execution instances of workflows.
    """
    workflow_id: str = Field(..., description="Workflow identifier")
    execution_id: str = Field(..., description="Unique execution identifier")
    result: Optional[str] = Field(None, description="Execution result")
    status: str = Field(..., description="Execution status")
    execution_time: Optional[float] = Field(None, description="Execution time in seconds")
    error: Optional[str] = Field(None, description="Error message if failed")
    created_at: datetime = Field(..., description="Execution start timestamp")

class ErrorResponse(BaseModel):
    """
    Standard error response model.
    
    Used for consistent error formatting across all API endpoints.
    Includes timestamp for debugging and optional detailed error information.
    """
    error: str = Field(..., description="Error message")
    details: Optional[str] = Field(None, description="Additional error details")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class FileUploadResponse(BaseModel):
    """
    Response model for file upload operations.

    Contains file metadata from the Paradigm API after successful upload.
    Files are processed and indexed automatically for use in workflows.
    """
    id: int = Field(..., description="File ID in Paradigm")
    filename: str = Field(..., description="Original filename")
    bytes: int = Field(..., description="File size in bytes")
    status: str = Field(default="uploaded", description="Processing status")
    created_at: Optional[int] = Field(default=None, description="Creation timestamp")
    purpose: Optional[str] = Field(default=None, description="File purpose")
    session_uuid: Optional[str] = Field(default=None, description="Upload session UUID")

class FileInfoResponse(BaseModel):
    """
    Response model for file information requests.
    
    Provides metadata about uploaded files and optionally their content.
    Used to check file status and retrieve file details.
    """
    id: int = Field(..., description="File ID")
    filename: str = Field(..., description="Filename")
    status: str = Field(..., description="Processing status")
    created_at: int = Field(..., description="Creation timestamp")
    purpose: str = Field(..., description="File purpose")
    content: Optional[str] = Field(None, description="File content if requested")

class WorkflowWithFilesRequest(BaseModel):
    """
    Request model for creating workflows that use uploaded files.
    
    Extends basic workflow creation with file attachment capabilities.
    The generated workflow will have access to the specified uploaded files.
    """
    description: str = Field(..., description="Natural language description of the workflow")
    name: Optional[str] = Field(None, description="Optional name for the workflow")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context for code generation")
    uploaded_file_ids: Optional[List[int]] = Field(None, description="List of uploaded file IDs to use in workflow")

class WorkflowDescriptionEnhanceRequest(BaseModel):
    """
    Request model for enhancing workflow descriptions.
    
    Takes a raw natural language description and uses AI to enhance it
    into a more detailed and actionable workflow specification.
    """
    description: str = Field(..., description="Raw natural language workflow description")

class WorkflowDescriptionEnhanceResponse(BaseModel):
    """
    Response model for workflow description enhancement.

    Contains the enhanced description along with questions and warnings
    to help users refine their workflow specifications.
    """
    enhanced_description: str = Field(..., description="Enhanced and detailed workflow description")
    questions: List[str] = Field(default_factory=list, description="Questions to clarify workflow requirements")
    warnings: List[str] = Field(default_factory=list, description="Warnings about tool limitations or requirements")


# ============================================================================
# Cell-Based Workflow Models
# ============================================================================

class CellStatusEnum(str, Enum):
    """
    Enumeration of cell execution status values for API responses.

    States:
        PENDING: Cell not yet generated or executed
        GENERATING: Code is being generated by Claude
        READY: Code generated, ready to execute
        EXECUTING: Cell is currently running
        COMPLETED: Cell finished successfully
        FAILED: Cell execution failed
        SKIPPED: Cell was skipped due to earlier failure
    """
    PENDING = "pending"
    GENERATING = "generating"
    READY = "ready"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class CellResponse(BaseModel):
    """
    Response model for a single workflow cell.

    Represents one discrete step in a cell-based workflow,
    including its definition, status, and execution results.
    Supports parallel execution via layer-based structure.
    """
    id: str = Field(..., description="Unique cell identifier")
    step_number: int = Field(..., description="Sequential position in workflow (1-indexed)")
    name: str = Field(..., description="Short descriptive name")
    description: str = Field(..., description="What this cell does")
    # Parallelization fields
    layer: int = Field(default=1, description="Execution layer (1, 2, 3...) - cells in same layer run in parallel")
    sublayer_index: int = Field(default=1, description="Position within layer (1, 2, 3...) for display as X.1, X.2")
    display_step: Optional[str] = Field(None, description="Display step number like '2.1', '2.3'")
    depends_on: List[str] = Field(default_factory=list, description="Step numbers this cell depends on for data")
    status: CellStatusEnum = Field(..., description="Current cell status")
    inputs_required: List[str] = Field(default_factory=list, description="Variable names needed from previous cells")
    outputs_produced: List[str] = Field(default_factory=list, description="Variable names this cell produces")
    paradigm_tools_used: List[str] = Field(default_factory=list, description="Paradigm API tools used")
    generated_code: Optional[str] = Field(None, description="Generated Python code for this cell")
    code_description: Optional[str] = Field(None, description="Human-readable explanation of what the code does")
    success_criteria: Optional[str] = Field(None, description="User-editable criteria for LLM validation")
    output: Optional[str] = Field(None, description="Human-readable output after execution")
    execution_time: Optional[float] = Field(None, description="Time taken to execute in seconds")
    error: Optional[str] = Field(None, description="Error message if cell failed")


class WorkflowPlanResponse(BaseModel):
    """
    Response model for a workflow plan.

    Contains the sequence of cells that make up the workflow,
    along with the shared context schema defining data flow.
    Supports parallel execution via layer-based structure.
    """
    id: str = Field(..., description="Unique plan identifier")
    total_cells: int = Field(..., description="Total number of cells in the plan")
    total_layers: int = Field(default=1, description="Total number of execution layers")
    is_parallel: bool = Field(default=False, description="Whether this plan has parallel layers")
    cells: List[CellResponse] = Field(default_factory=list, description="List of workflow cells")
    shared_context_schema: Dict[str, str] = Field(
        default_factory=dict,
        description="Variable name to type description mapping"
    )
    status: str = Field(..., description="Current plan status")


class CellBasedWorkflowResponse(BaseModel):
    """
    Response model for cell-based workflows.

    Extended workflow response that includes the plan and cells
    for step-by-step execution visibility.
    """
    id: str = Field(..., description="Unique workflow identifier")
    name: Optional[str] = Field(None, description="Workflow name")
    description: str = Field(..., description="Workflow description")
    status: str = Field(..., description="Current workflow status")
    execution_mode: str = Field(default="cell_based", description="Execution mode: cell_based or monolithic")
    plan: Optional[WorkflowPlanResponse] = Field(None, description="Workflow plan with cell definitions")
    cells: Optional[List[CellResponse]] = Field(None, description="List of workflow cells")
    generated_code: Optional[str] = Field(None, description="Full generated code (for monolithic mode)")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    error: Optional[str] = Field(None, description="Error message if failed")


class CellExecutionEvent(BaseModel):
    """
    Model for cell execution events streamed via SSE.

    Used to communicate real-time progress during cell-based
    workflow execution.
    """
    type: str = Field(..., description="Event type: workflow_start, cell_generating, cell_ready, cell_executing, cell_completed, cell_failed, workflow_completed, workflow_failed")
    cell_id: Optional[str] = Field(None, description="Cell identifier (if applicable)")
    cell_name: Optional[str] = Field(None, description="Cell name (if applicable)")
    step_number: Optional[int] = Field(None, description="Step number (if applicable)")
    total_cells: Optional[int] = Field(None, description="Total cells (for workflow_start)")
    output: Optional[str] = Field(None, description="Cell output (for cell_completed)")
    variables: Optional[List[str]] = Field(None, description="Variable names produced (for cell_completed)")
    execution_time: Optional[float] = Field(None, description="Execution time in seconds")
    error: Optional[str] = Field(None, description="Error message (for failures)")
    final_result: Optional[str] = Field(None, description="Final result (for workflow_completed)")
    completed_cells: Optional[int] = Field(None, description="Number of completed cells (for workflow_failed)")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Event timestamp")


class CellBasedExecuteRequest(BaseModel):
    """
    Request model for executing a cell-based workflow.

    Similar to WorkflowExecuteRequest but explicitly for cell-based execution
    with streaming response.
    """
    user_input: str = Field(..., description="Input data to process through the workflow")
    attached_file_ids: Optional[List[int]] = Field(None, description="List of file IDs attached to this query")
    stream: bool = Field(default=True, description="Whether to stream results via SSE")


class ExampleInput(BaseModel):
    """
    Input for a single example in multi-example execution.

    Each example has its own user input and optional file attachments.
    """
    id: Optional[str] = Field(None, description="Optional identifier for this example")
    user_input: str = Field(..., description="User input for this example")
    attached_file_ids: Optional[List[int]] = Field(None, description="File IDs for this example")


class ExecuteWithEvaluationRequest(BaseModel):
    """
    Request model for executing a workflow with LLM-as-judge evaluation.

    Uses the smoke test approach:
    1. Execute first example and evaluate the output
    2. If evaluation fails, fix code and retry (up to 5 times)
    3. Once evaluation passes, run remaining examples

    This ensures code quality before running all examples.
    """
    examples: List[ExampleInput] = Field(
        ...,
        description="List of example inputs to run through the workflow",
        min_length=1
    )


class CellFeedbackRequest(BaseModel):
    """
    Request model for submitting feedback on a cell's generated code.

    Used when users want to provide feedback and request changes to
    a cell's generated code. The system will regenerate the code
    incorporating the feedback.
    """
    feedback: str = Field(..., description="User feedback describing desired changes to the cell code")


class SuccessCriteriaRequest(BaseModel):
    """
    Request model for updating a cell's success criteria.

    Used when users want to edit the validation criteria for a cell's output.
    After updating, the cell will be reset and re-executed with the new criteria.
    """
    success_criteria: str = Field(..., description="Custom success criteria for LLM validation")


class CellExecuteSingleRequest(BaseModel):
    """
    Request model for executing a single cell with specific input.

    Used for cell-by-cell execution where each cell runs for all examples
    before moving to the next cell.
    """
    user_input: str = Field(..., description="User query for this execution")
    attached_file_ids: Optional[List[int]] = Field(None, description="Optional list of file IDs")
    execution_context: Optional[Dict[str, Any]] = Field(None, description="Context from previous cells")

