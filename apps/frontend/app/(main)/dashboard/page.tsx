"use client";

import * as React from "react";

import { DataTable } from "@/components/custom/data-table";
import { workflowColumns } from "@/components/custom/workflow-columns";
import { DashboardHeader } from "@/components/custom/dashboard-header";
import { useWorkflows } from "@/hooks/use-workflows";
import { IconLoader2, IconAlertCircle } from "@tabler/icons-react";
import { Button } from "@/components/ui/button";

export default function Page() {
  const [pagination, setPagination] = React.useState({
    pageIndex: 0,
    pageSize: 10,
  });

  const { data, isLoading, error, refetch } = useWorkflows(
    pagination.pageSize,
    pagination.pageIndex * pagination.pageSize
  );

  const workflowsResult = data || { workflows: [], total: 0 };
  const pageCount = Math.ceil(workflowsResult.total / pagination.pageSize);

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] gap-4">
        <IconLoader2 className="size-8 animate-spin text-primary" />
        <p className="text-muted-foreground animate-pulse">
          Loading your dashboard...
        </p>
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
    <div className="flex flex-col gap-2">
      <DashboardHeader workflows={workflowsResult.workflows} userName="Shreekar" />
      <div className="px-4 lg:px-6 pb-12">
        <DataTable
          data={workflowsResult.workflows}
          columns={workflowColumns}
          addLabel="New Workflow"
          onAddClick={() => console.log("New workflow clicked")}
          manualPagination={true}
          pageCount={pageCount}
          paginationState={pagination}
          onPaginationChange={setPagination}
        />
      </div>
    </div>
  );
}
