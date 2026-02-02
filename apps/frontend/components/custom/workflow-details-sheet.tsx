"use client";

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { WorkflowListItem } from "@/schema/generated/workflows";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import {
  IconFileText,
  IconExternalLink,
  IconCircleCheckFilled,
  IconLoader2,
  IconCircleXFilled,
  IconClock,
  IconChevronRight,
} from "@tabler/icons-react";
import { format } from "date-fns";
import { Button } from "@/components/ui/button";

interface WorkflowDetailsSheetProps {
  workflow: WorkflowListItem | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function WorkflowDetailsSheet({
  workflow,
  open,
  onOpenChange,
}: WorkflowDetailsSheetProps) {
  if (!workflow) return null;

  const stageStatusIcon = (status?: string) => {
    switch (status?.toLowerCase()) {
      case "completed":
        return <IconCircleCheckFilled className="size-4 text-emerald-500" />;
      case "running":
        return <IconLoader2 className="size-4 text-blue-500 animate-spin" />;
      case "failed":
        return <IconCircleXFilled className="size-4 text-red-500" />;
      default:
        return <IconClock className="size-4 text-muted-foreground" />;
    }
  };

  const getStatusBadge = (status?: string) => {
    const s = status?.toLowerCase() || "unknown";
    const configs: Record<string, string> = {
      completed: "text-emerald-500 bg-emerald-500/10 border-emerald-500/20",
      running: "text-blue-500 bg-blue-500/10 border-blue-500/20",
      failed: "text-red-500 bg-red-500/10 border-red-500/20",
      pending: "text-amber-500 bg-amber-500/10 border-amber-500/20",
    };
    return (
      <Badge
        variant="outline"
        className={`${configs[s] || ""} capitalize rounded`}
      >
        {s}
      </Badge>
    );
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        className="w-[500px] sm:max-w-[100vw] p-0 flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <SheetHeader className="px-6 pt-6 border-b">
          <div className="flex items-center justify-between">
            <SheetTitle className="text-xl font-semibold overflow-hidden text-ellipsis whitespace-nowrap">
              {workflow.workflow_name}
            </SheetTitle>
            {getStatusBadge(workflow.status)}
          </div>
        </SheetHeader>

        <ScrollArea className="flex-1 px-6 py-4">
          <div className="space-y-8">
            {/* Documents Section */}
            <section>
              <div className="flex items-center gap-2 mb-2">
                <IconFileText className="size-5 text-primary" />
                <h3 className="font-semibold text-foreground">Documents</h3>
                <Badge variant="secondary" className="ml-auto rounded">
                  {workflow.documents?.length || 0}
                </Badge>
              </div>
              <div className="grid gap-3">
                {workflow.documents && workflow.documents.length > 0 ? (
                  workflow.documents.map((doc) => (
                    <div
                      key={doc.document_id}
                      className="group relative flex items-center gap-4 p-3 rounded border bg-card hover:bg-accent/50 transition-all duration-200"
                    >
                      <div className="size-10 rounded bg-primary/10 flex items-center justify-center">
                        <IconFileText className="size-5 text-primary" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-foreground truncate">
                          {doc.document_name || doc.file_name}
                        </p>
                      </div>
                      {doc.file_path && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="opacity-0 rounded group-hover:opacity-100 transition-opacity"
                          onClick={() => window.open(doc.file_path!, "_blank")}
                        >
                          <IconExternalLink className="size-4" />
                        </Button>
                      )}
                    </div>
                  ))
                ) : (
                  <p className="text-sm text-muted-foreground italic">
                    No documents found for this workflow.
                  </p>
                )}
              </div>
            </section>

            <Separator />

            {/* Stages Section */}
            <section>
              <div className="flex items-center gap-2 mb-4">
                <IconLoader2 className="size-5 text-primary" />
                <h3 className="font-semibold text-foreground">
                  Processing Stages
                </h3>
              </div>
              <div className="relative pl-6 space-y-4">
                {workflow.stages && workflow.stages.length > 0 ? (
                  workflow.stages.map((stage, idx) => (
                    <div key={idx} className="relative px-4">
                      <div className="absolute -left-[22px] top-1 p-1 bg-background">
                        {stageStatusIcon(stage.status)}
                      </div>
                      <div className="flex flex-col gap-1">
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-medium text-foreground leading-none">
                            {stage.stage_name}
                          </span>
                          {stage.duration_seconds && (
                            <span className="text-xs text-muted-foreground">
                              {stage.duration_seconds.toFixed(1)}s
                            </span>
                          )}
                        </div>
                        {stage.completed_at && (
                          <span className="text-[10px] text-muted-foreground uppercase tracking-tight">
                            Completed at{" "}
                            {format(
                              new Date(stage.completed_at),
                              "MMM d, HH:mm:ss",
                            )}
                          </span>
                        )}
                      </div>
                    </div>
                  ))
                ) : (
                  <p className="text-sm text-muted-foreground italic pl-2">
                    No stage data available yet.
                  </p>
                )}
              </div>
            </section>

            {/* General Info Section */}
            <section className="bg-muted/30 rounded p-4 space-y-3 border border-border/50">
              <div className="flex justify-between text-xs">
                <span className="text-muted-foreground">Started at</span>
                <span className="text-foreground font-medium">
                  {workflow.created_at
                    ? format(
                        new Date(workflow.created_at),
                        "MMM d, yyyy HH:mm:ss",
                      )
                    : "-"}
                </span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-muted-foreground">Last Updated</span>
                <span className="text-foreground font-medium">
                  {workflow.updated_at
                    ? format(
                        new Date(workflow.updated_at),
                        "MMM d, yyyy HH:mm:ss",
                      )
                    : "-"}
                </span>
              </div>
              {workflow.duration_seconds && (
                <div className="flex justify-between text-xs">
                  <span className="text-muted-foreground">Total Duration</span>
                  <span className="text-foreground font-medium">
                    {workflow.duration_seconds.toFixed(1)}s
                  </span>
                </div>
              )}
            </section>
          </div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}
