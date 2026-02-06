"use client";

import React from "react";
import { useParams, useRouter } from "next/navigation";
import {
  useWorkflowsByDefinitionId,
  useCreateWorkflow,
} from "@/hooks/use-workflows";
import { workflowColumns } from "@/components/custom/workflow-columns";
import { DataTable } from "@/components/custom/data-table";
import { toast } from "sonner";

// icons
import { IconLoader2, IconAlertCircle } from "@tabler/icons-react";

// ui components
import { Button } from "@/components/ui/button";
import { TableSkeleton } from "@/components/custom/table-skeleton";

export default function WorkflowExecutionPage() {
  const params = useParams();
  const router = useRouter();
  const workflowDefinitionId = params.id as string;

  const createWorkflow = useCreateWorkflow();

  const [pagination, setPagination] = React.useState({
    pageIndex: 0,
    pageSize: 10,
  });

  const { data, isLoading, error, refetch } = useWorkflowsByDefinitionId(
    workflowDefinitionId as string,
    pagination.pageSize,
    pagination.pageIndex * pagination.pageSize,
  );

  const workflowsResult = data || { workflows: [], total: 0 };
  const pageCount = Math.ceil(workflowsResult.total / pagination.pageSize);

  const handleCreateNewWorkflow = async (workflowDefinitionId: string) => {
    try {
      const result = await createWorkflow.mutateAsync({
        workflow_definition_id: workflowDefinitionId,
        workflow_name: "Untitled",
      });

      if (result.status && result.data?.workflow_id) {
        toast.success("Workflow blueprint created");
        router.push(`/workflow-execution/${result.data.workflow_id}`);
      } else {
        toast.error("Failed to create workflow blueprint");
      }
    } catch (error) {
      console.error("Error creating workflow blueprint:", error);
      toast.error("An error occurred while creating the workflow blueprint");
    }
  };

  if (isLoading) {
    return (
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-1 px-4 lg:px-6 pt-4">
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">
            Workflow Overview
          </h1>
          <p className="text-sm text-muted-foreground">
            Manage and monitor your workflow executions.
          </p>
        </div>
        <TableSkeleton />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] gap-4">
        <div className="p-4 rounded-full bg-red-50 dark:bg-red-500/10 text-red-600">
          <IconAlertCircle className="size-8" />
        </div>
        <p className="text-foreground font-medium">Something went wrong</p>
        <p className="text-muted-foreground text-sm">
          {error instanceof Error ? error.message : "Failed to fetch workflows"}
        </p>
        <Button onClick={() => refetch()} variant="outline">
          Try Again
        </Button>
      </div>
    );
  }

  return (
    <DataTable
      title="Workflows"
      data={workflowsResult.workflows}
      columns={workflowColumns}
      addLabel="New Workflow"
      onAddClick={() => handleCreateNewWorkflow(workflowDefinitionId as string)}
      manualPagination={true}
      pageCount={pageCount}
      paginationState={pagination}
      onPaginationChange={setPagination}
      workflowDefinitionId={workflowDefinitionId as string}
      total={workflowsResult.total}
    />
  );
}
