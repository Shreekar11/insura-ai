from typing import Dict, List, Type, Optional, Callable
from dataclasses import dataclass
from enum import Enum

class WorkflowType(str, Enum):
    """Workflow categories."""
    CORE = "core"
    SHARED = "shared"
    BUSINESS = "business"
    POLICY_COMPARISON = "policy_comparison"
    PROPOSAL_GENERATION = "proposal_generation"
    CLAIMS_PROCESSING = "claims_processing"

@dataclass
class WorkflowMetadata:
    """Metadata for workflow discovery."""
    workflow_class: Type
    name: str
    category: WorkflowType
    task_queue: str
    dependencies: List[str]  # Other workflows it depends on

class WorkflowRegistry:
    """Central registry for all workflows."""
    
    _workflows: Dict[str, WorkflowMetadata] = {}
    
    @classmethod
    def register(
        cls,
        category: WorkflowType,
        task_queue: str = "documents-queue",
        dependencies: List[str] = None
    ):
        """Decorator to register a workflow."""
        def decorator(workflow_class):
            metadata = WorkflowMetadata(
                workflow_class=workflow_class,
                name=workflow_class.__name__,
                category=category,
                task_queue=task_queue,
                dependencies=dependencies or []
            )
            cls._workflows[workflow_class.__name__] = metadata
            return workflow_class
        return decorator
    
    @classmethod
    def get_all_workflows(cls) -> Dict[str, WorkflowMetadata]:
        """Get all registered workflows."""
        return cls._workflows
    
    @classmethod
    def get_by_category(cls, category: WorkflowType) -> List[WorkflowMetadata]:
        """Get workflows by category."""
        return [w for w in cls._workflows.values() if w.category == category]
