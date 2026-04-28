"""
Unit tests for workflow domain models.

Tests the data contracts: serialization roundtrips, status transitions,
and layer grouping logic. These are the foundation for all workflow operations.
"""

import pytest
from api.workflow.models import (
    Workflow,
    WorkflowExecution,
    ExecutionStatus,
    WorkflowCell,
    WorkflowPlan,
    CellStatus,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# WorkflowCell
# ---------------------------------------------------------------------------

class TestWorkflowCell:
    """Tests for WorkflowCell data contract."""

    def test_to_dict_from_dict_roundtrip(self):
        """Serialized cell can be deserialized back to an equivalent cell."""
        cell = WorkflowCell(
            workflow_id="wf-1",
            step_number=2,
            name="Search Docs",
            description="Search documents for relevant info",
            layer=1,
            sublayer_index=1,
            depends_on=["cell-0"],
            inputs_required=["user_input"],
            outputs_produced=["search_results"],
            paradigm_tools_used=["document_search"],
            generated_code="async def execute_cell(ctx): return {}",
            code_description="Searches documents",
            success_criteria="Returns non-empty results",
        )
        data = cell.to_dict()
        restored = WorkflowCell.from_dict(data)

        assert restored.workflow_id == cell.workflow_id
        assert restored.step_number == cell.step_number
        assert restored.name == cell.name
        assert restored.layer == cell.layer
        assert restored.inputs_required == cell.inputs_required
        assert restored.outputs_produced == cell.outputs_produced
        assert restored.generated_code == cell.generated_code
        assert restored.status == cell.status

    def test_status_transitions(self):
        """Cell transitions through the expected lifecycle."""
        cell = WorkflowCell()
        assert cell.status == CellStatus.PENDING

        cell.mark_generating()
        assert cell.status == CellStatus.GENERATING

        cell.mark_ready("print('hello')", code_description="Prints hello")
        assert cell.status == CellStatus.READY
        assert cell.generated_code == "print('hello')"
        assert cell.code_description == "Prints hello"

        cell.mark_executing()
        assert cell.status == CellStatus.EXECUTING

        cell.mark_completed("output text", {"result": 42}, 1.5)
        assert cell.status == CellStatus.COMPLETED
        assert cell.output == "output text"
        assert cell.output_variables == {"result": 42}
        assert cell.execution_time == 1.5
        assert cell.executed_at is not None

    def test_mark_failed(self):
        """mark_failed sets error, status, and executed_at."""
        cell = WorkflowCell()
        cell.mark_failed("boom", execution_time=0.3)
        assert cell.status == CellStatus.FAILED
        assert cell.error == "boom"
        assert cell.execution_time == 0.3
        assert cell.executed_at is not None

    def test_mark_skipped(self):
        """mark_skipped sets status to SKIPPED."""
        cell = WorkflowCell()
        cell.mark_skipped()
        assert cell.status == CellStatus.SKIPPED

    def test_get_display_step(self):
        """Display step formats as 'layer.sublayer'."""
        cell = WorkflowCell(layer=2, sublayer_index=3)
        assert cell.get_display_step() == "2.3"

    def test_from_dict_parses_status_string(self):
        """from_dict converts a status string to the CellStatus enum."""
        data = {"status": "completed", "name": "test"}
        cell = WorkflowCell.from_dict(data)
        assert cell.status == CellStatus.COMPLETED


# ---------------------------------------------------------------------------
# WorkflowPlan
# ---------------------------------------------------------------------------

class TestWorkflowPlan:
    """Tests for WorkflowPlan data contract."""

    def _make_plan(self):
        """Helper: plan with 4 cells across 3 layers (layer 2 is parallel)."""
        plan = WorkflowPlan(description="test plan")
        plan.cells = [
            WorkflowCell(step_number=1, name="A", layer=1, sublayer_index=1),
            WorkflowCell(step_number=2, name="B", layer=2, sublayer_index=1),
            WorkflowCell(step_number=3, name="C", layer=2, sublayer_index=2),
            WorkflowCell(step_number=4, name="D", layer=3, sublayer_index=1),
        ]
        return plan

    def test_to_dict_from_dict_roundtrip(self):
        """Plan survives serialization roundtrip with cells intact."""
        plan = self._make_plan()
        plan.shared_context_schema = {"result": "str"}
        data = plan.to_dict()
        restored = WorkflowPlan.from_dict(data)

        assert restored.description == plan.description
        assert len(restored.cells) == 4
        assert restored.shared_context_schema == {"result": "str"}
        assert restored.cells[0].name == "A"

    def test_get_cells_by_layer(self):
        """Cells are grouped correctly by layer number."""
        plan = self._make_plan()
        layers = plan.get_cells_by_layer()
        assert len(layers[1]) == 1
        assert len(layers[2]) == 2
        assert len(layers[3]) == 1

    def test_get_max_layer(self):
        """Returns the highest layer number."""
        plan = self._make_plan()
        assert plan.get_max_layer() == 3

    def test_get_max_layer_empty(self):
        """Returns 0 when there are no cells."""
        plan = WorkflowPlan()
        assert plan.get_max_layer() == 0

    def test_is_parallel_workflow(self):
        """Detects parallel workflows (any layer with >1 cell)."""
        plan = self._make_plan()
        assert plan.is_parallel_workflow() is True

        # Sequential-only plan
        seq_plan = WorkflowPlan()
        seq_plan.cells = [
            WorkflowCell(layer=1, sublayer_index=1),
            WorkflowCell(layer=2, sublayer_index=1),
        ]
        assert seq_plan.is_parallel_workflow() is False


# ---------------------------------------------------------------------------
# Workflow & WorkflowExecution
# ---------------------------------------------------------------------------

class TestWorkflow:
    """Tests for Workflow status updates."""

    def test_update_status(self):
        """update_status sets status, updated_at, and optional error."""
        wf = Workflow(description="test")
        old_ts = wf.updated_at

        wf.update_status("failed", error="something broke")
        assert wf.status == "failed"
        assert wf.error == "something broke"
        assert wf.updated_at >= old_ts


class TestWorkflowExecution:
    """Tests for WorkflowExecution lifecycle."""

    def test_mark_completed(self):
        """mark_completed sets result, status, time, and timestamp."""
        ex = WorkflowExecution(workflow_id="wf-1")
        ex.mark_completed("done", 2.5)
        assert ex.status == ExecutionStatus.COMPLETED
        assert ex.result == "done"
        assert ex.execution_time == 2.5
        assert ex.completed_at is not None

    def test_mark_failed(self):
        """mark_failed sets error, status, and timestamp."""
        ex = WorkflowExecution(workflow_id="wf-1")
        ex.mark_failed("timeout")
        assert ex.status == ExecutionStatus.FAILED
        assert ex.error == "timeout"
        assert ex.completed_at is not None
