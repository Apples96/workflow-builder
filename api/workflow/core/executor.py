import logging
import json
import os
from typing import Optional, Dict, Any
from ..models import Workflow, WorkflowPlan
from ...config import settings

logger = logging.getLogger(__name__)

# Support both Vercel KV environment variables and direct Upstash variables
try:
    from upstash_redis import Redis

    redis_url = os.getenv("KV_REST_API_URL") or os.getenv("UPSTASH_REDIS_REST_URL")
    redis_token = os.getenv("KV_REST_API_TOKEN") or os.getenv("UPSTASH_REDIS_REST_TOKEN")

    redis_client = Redis(
        url=redis_url,
        token=redis_token
    ) if redis_url and redis_token else None

    if redis_client:
        logger.info(f"✅ Redis configured using {'Vercel KV' if os.getenv('KV_REST_API_URL') else 'Upstash'} variables")
except ImportError:
    redis_client = None
    logger.warning("⚠️ upstash-redis not installed, using in-memory storage")

class WorkflowExecutor:
    def __init__(self):
        self.max_execution_time = settings.max_execution_time
        self.use_redis = redis_client is not None
        self.workflows: Dict[str, Workflow] = {}
        self.workflow_plans: Dict[str, WorkflowPlan] = {}
        self.execution_contexts: Dict[str, Dict[str, Any]] = {}

        if self.use_redis:
            logger.info("✅ Using Redis (Upstash) for workflow storage")
        else:
            if not settings.debug:
                logger.warning(
                    "⚠️ WARNING: Running without Redis — workflow state will be lost on server restart. "
                    "Set KV_REST_API_URL and KV_REST_API_TOKEN environment variables for persistent storage."
                )
            else:
                logger.warning("⚠️ Using in-memory storage (not suitable for serverless)")

    def store_workflow(self, workflow: Workflow) -> None:
        """Store a workflow for later execution"""
        if self.use_redis:
            workflow_dict = {
                "id": workflow.id,
                "name": workflow.name,
                "description": workflow.description,
                "generated_code": workflow.generated_code,
                "status": workflow.status,
                "created_at": workflow.created_at.isoformat() if workflow.created_at else None,
                "updated_at": workflow.updated_at.isoformat() if workflow.updated_at else None,
                "error": workflow.error,
                "context": workflow.context
            }
            workflow_data = json.dumps(workflow_dict)
            redis_client.setex(
                f"workflow:{workflow.id}",
                86400,  # 24 hours TTL
                workflow_data
            )
            logger.info(f"✅ Stored workflow {workflow.id} in Redis")
        else:
            self.workflows[workflow.id] = workflow

    def get_workflow(self, workflow_id: str) -> Optional[Workflow]:
        """Retrieve a stored workflow"""
        if self.use_redis:
            workflow_data = redis_client.get("workflow:{}".format(workflow_id))
            if workflow_data:
                workflow_dict = json.loads(workflow_data)
                return Workflow(**workflow_dict)
            return None
        else:
            return self.workflows.get(workflow_id)

    def store_workflow_plan(self, workflow_id: str, plan: WorkflowPlan) -> None:
        """Store a workflow plan for cell-based execution."""
        if self.use_redis:
            plan_data = json.dumps(plan.to_dict())
            redis_client.setex(
                "workflow_plan:{}".format(workflow_id),
                86400,  # 24 hours TTL
                plan_data
            )
            logger.info("Stored workflow plan for {} in Redis".format(workflow_id))
        else:
            self.workflow_plans[workflow_id] = plan
            logger.info("Stored workflow plan for {} in memory".format(workflow_id))

    def get_workflow_plan(self, workflow_id: str) -> Optional[WorkflowPlan]:
        """Retrieve a workflow plan, or None if not found."""
        if self.use_redis:
            plan_data = redis_client.get("workflow_plan:{}".format(workflow_id))
            if plan_data:
                plan_dict = json.loads(plan_data)
                return WorkflowPlan.from_dict(plan_dict)
            return None
        else:
            return self.workflow_plans.get(workflow_id)

    def store_execution_context(self, workflow_id: str, context: Dict[str, Any]) -> None:
        """Store execution context for a workflow (for cell reruns)."""
        if self.use_redis:
            context_data = json.dumps(context, default=str)
            redis_client.setex(
                "execution_context:{}".format(workflow_id),
                86400,  # 24 hours TTL
                context_data
            )
        else:
            self.execution_contexts[workflow_id] = context

    def get_execution_context(self, workflow_id: str) -> Dict[str, Any]:
        """Retrieve execution context for a workflow, or empty dict if not found."""
        if self.use_redis:
            context_data = redis_client.get("execution_context:{}".format(workflow_id))
            if context_data:
                return json.loads(context_data)
            return {}
        else:
            return self.execution_contexts.get(workflow_id, {})

workflow_executor = WorkflowExecutor()