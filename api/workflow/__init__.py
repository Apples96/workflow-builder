# Workflow module - provides workflow generation, execution, and packaging capabilities
#
# Directory structure:
#   core/       - Core infrastructure (executor, generator, enhancer)
#   cell/       - Cell-based execution system (planner, generator, executor, evaluator, combiner)
#   generators/ - Package generators (workflow package, MCP package)
#   prompts/    - LLM prompt templates (markdown files)
#   templates/  - Code templates for package generation
#
# Re-exports for backward compatibility:
from .core import (
    WorkflowExecutor,
    workflow_executor,
    WorkflowGenerator,
    workflow_generator,
    WorkflowEnhancer,
    WorkflowProgressEnhancer,
    analyze_workflow_for_ui,
    generate_simple_description,
)

from .cell import (
    WorkflowPlanner,
    CellCodeGenerator,
    CellExecutor,
    CellOutputEvaluator,
    WorkflowCombiner,
)

from .generators import (
    WorkflowPackageGenerator,
    MCPPackageGenerator,
)

from .models import (
    Workflow,
    WorkflowExecution,
    ExecutionStatus,
    WorkflowPlan,
    WorkflowCell,
    CellStatus,
)

__all__ = [
    # Core
    "WorkflowExecutor",
    "workflow_executor",
    "WorkflowGenerator",
    "workflow_generator",
    "WorkflowEnhancer",
    "WorkflowProgressEnhancer",
    "analyze_workflow_for_ui",
    "generate_simple_description",
    # Cell-based
    "WorkflowPlanner",
    "CellCodeGenerator",
    "CellExecutor",
    "CellOutputEvaluator",
    "WorkflowCombiner",
    # Generators
    "WorkflowPackageGenerator",
    "MCPPackageGenerator",
    # Models
    "Workflow",
    "WorkflowExecution",
    "ExecutionStatus",
    "WorkflowPlan",
    "WorkflowCell",
    "CellStatus",
]
