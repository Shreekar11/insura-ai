"use client";

import * as React from "react";

import { useRouter } from "next/navigation";
import { DataTable } from "@/components/custom/data-table";
import { workflowColumns } from "@/components/custom/workflow-columns";
import { DashboardHeader } from "@/components/custom/dashboard-header";
import { useWorkflows, useCreateWorkflow } from "@/hooks/use-workflows";
import { useWorkflowDefinitions } from "@/hooks/use-workflow-definitions";
import { IconLoader2, IconAlertCircle } from "@tabler/icons-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { useAuth } from "@/contexts/auth-context";
import { TableSkeleton } from "@/components/custom/table-skeleton";

export default function Page() {
  const router = useRouter();
  const { user } = useAuth();
  const createWorkflow = useCreateWorkflow();
  const { data: workflowDefinitions } = useWorkflowDefinitions();

  const [pagination, setPagination] = React.useState({
    pageIndex: 0,
    pageSize: 10,
  });

  const { data, isLoading, error, refetch } = useWorkflows(
    pagination.pageSize,
    pagination.pageIndex * pagination.pageSize,
  );

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

  const workflowsResult = data || { workflows: [], total: 0 };
  const pageCount = Math.ceil(workflowsResult.total / pagination.pageSize);

  if (isLoading) {
    return (
      <div className="flex flex-col gap-2 pt-2">
        <DashboardHeader workflows={[]} userName={user?.user_metadata.name} />
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
    <div className="flex flex-col gap-2 pt-2">
      <DashboardHeader
        workflows={workflowsResult.workflows}
        userName={user?.user_metadata.name}
      />
      <DataTable
        data={workflowsResult.workflows}
        columns={workflowColumns}
        addLabel="New Workflow"
        onAddClick={handleCreateNewWorkflow}
        workflowDefinitions={workflowDefinitions}
        manualPagination={true}
        pageCount={pageCount}
        paginationState={pagination}
        onPaginationChange={setPagination}
      />
    </div>
  );
}
