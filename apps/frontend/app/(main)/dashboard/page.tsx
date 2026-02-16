"use client";

import * as React from "react";

import { useRouter } from "next/navigation";
import { DataTable } from "@/components/custom/data-table";
import { workflowColumns } from "@/components/custom/workflow-columns";
import { DashboardHeader } from "@/components/custom/dashboard-header";
import { useWorkflows, useCreateWorkflow } from "@/hooks/use-workflows";
import { useWorkflowDefinitions } from "@/hooks/use-workflow-definitions";
import {
  IconAlertCircle,
  IconArrowRight,
} from "@tabler/icons-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { useAuth } from "@/contexts/auth-context";
import { TableSkeleton } from "@/components/custom/table-skeleton";
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import Image from "next/image";

import policyComparisonImg from "../../../public/assets/policy-comparison.png";
import proposalGenerationImg from "../../../public/assets/proposal-generation.png";
import quoteComparisonImg from "../../../public/assets/quote-comparison.jpeg";

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
        <DashboardHeader userName={user?.user_metadata.name} />
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
      <DashboardHeader userName={user?.user_metadata.name} />
      {workflowsResult.workflows.length === 0 ? (
        <div className="flex flex-col gap-8 px-4 lg:px-6 py-2">
          <div className="flex flex-col gap-2">
            <h2 className="text-xl font-semibold tracking-tight">
              Choose a workflow to automate your insurance operations
            </h2>
            <p className="text-muted-foreground">
              Select a prebuilt workflow to start automating insurance operations.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[
              {
                key: "policy_comparison",
                title: "Policy Comparison",
                description:
                  "Deep dive into policy differences with AI-powered analysis.",
                image: policyComparisonImg,
              },
              {
                key: "proposal_generation",
                title: "Proposal Generation",
                description:
                  "Automate complex proposal drafting with multi-document reasoning.",
                image: proposalGenerationImg,
              },
              {
                key: "quote_comparison",
                title: "Quote Comparison",
                description:
                  "Bridge the gap between quotes with granular coverage matching.",
                image: quoteComparisonImg,
              },
            ].map((card) => {
              const definition = workflowDefinitions?.find(
                (d) => d.key === card.key,
              );
              return (
                <Card
                  key={card.key}
                  className="pt-0 overflow-hidden rounded-lg cursor-pointer transition-all group"
                  onClick={() =>
                    definition && handleCreateNewWorkflow(definition.id!)
                  }
                >
                  <div className="relative h-48 w-full">
                    <Image
                      src={card.image}
                      alt={card.title}
                      fill
                      className="object-cover transition-transform group-hover:scale-105"
                    />
                  </div>
                  <CardHeader>
                    <CardTitle className="flex items-center justify-between">
                      {card.title}
                      <IconArrowRight className="size-4 opacity-0 -translate-x-2 group-hover:opacity-100 group-hover:translate-x-0 transition-all" />
                    </CardTitle>
                    <CardDescription>{card.description}</CardDescription>
                  </CardHeader>
                </Card>
              );
            })}
          </div>
        </div>
      ) : (
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
      )}
    </div>
  );
}
