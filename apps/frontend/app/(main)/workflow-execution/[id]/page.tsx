"use client";

import { useParams } from "next/navigation";
import { useWorkflowById } from "@/hooks/use-workflows";
import { IconLoader2 } from "@tabler/icons-react";

export default function WorkflowExecutionPage() {
  const { id } = useParams();
  const workflowId = id as string;

  const { data: workflow, isLoading: isLoadingWorkflow } = useWorkflowById(workflowId);

  if (isLoadingWorkflow) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <IconLoader2 className="animate-spin size-8 text-primary" />
      </div>
    );
  }

  return (
    <div className="">
        Workflow Execution
    </div>
  );
}
