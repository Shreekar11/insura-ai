"use client";

import { useState, useCallback, useEffect } from "react";
import { useParams } from "next/navigation";
import { useWorkflowById, useExecuteWorkflow } from "@/hooks/use-workflows";
import { useUploadDocument, useDocuments } from "@/hooks/use-documents";
import {
  FileDropzone,
  type UploadedFile,
} from "@/components/custom/file-dropzone";
import { Button } from "@/components/ui/button";
import { IconLoader2, IconPlayerPlay } from "@tabler/icons-react";
import { Sparkles } from "lucide-react";
import { useWorkflowStream } from "@/hooks/use-workflow-stream";
import { WorkflowTimeline } from "@/components/custom/workflow-timeline";
import { toast } from "sonner";
import { useActiveWorkflow } from "@/contexts/active-workflow-context";
import { cn } from "@/lib/utils";

import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { PageHeader } from "@/components/layout/page-header";
import { ExtractionOutputSidebar } from "@/components/custom/extraction-output-sidebar";
import {
  PDFHighlightProvider,
  usePDFHighlight,
} from "@/contexts/pdf-highlight-context";
import { PDFViewerPanel } from "@/components/custom/pdf-viewer/pdf-viewer-panel";
import { ComparisonOutputSidebar } from "@/components/custom/comparison-output-sidebar";

function WorkflowExecutionContent() {
  const { id } = useParams();
  const workflowId = id as string;
  const { pdfViewerOpen, pdfUrl, activeCitation, clearHighlight } =
    usePDFHighlight();

  const { data: workflow, isLoading: isLoadingWorkflow } =
    useWorkflowById(workflowId);
  const { data: existingDocuments, isLoading: isLoadingDocuments } =
    useDocuments(workflowId);
  const uploadMutation = useUploadDocument();
  const executeMutation = useExecuteWorkflow();

  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
  const [isStarted, setIsStarted] = useState(false);

  // Sidebar states
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [comparisonSidebarOpen, setComparisonSidebarOpen] = useState(false);
  const [selectedOutput, setSelectedOutput] = useState<{
    workflowId: string;
    documentId: string;
  } | null>(null);

  // SSE Stream
  const { events, isConnected, isComplete } = useWorkflowStream(
    isStarted ? workflowId : null,
  );

  const { setActiveWorkflowDefinitionId } = useActiveWorkflow();

  // Sync existing documents to local state and rehydrate isStarted
  useEffect(() => {
    if (workflow?.definition_id) {
      setActiveWorkflowDefinitionId(workflow.definition_id);
    }

    if (workflow?.status && workflow.status !== "draft") {
      setIsStarted(true);
    }

    if (existingDocuments?.documents) {
      setUploadedFiles((prev) => {
        const existingIds = new Set(prev.map((f) => f.id));
        const newFiles = existingDocuments.documents
          .filter((doc) => !existingIds.has(doc.id))
          .map((doc) => ({
            id: doc.id,
            name: doc.document_name || "Untitled",
            status: "success" as const,
          }));

        if (newFiles.length === 0) return prev;
        return [...prev, ...newFiles];
      });
    }
  }, [existingDocuments, workflow, setActiveWorkflowDefinitionId]);

  const handleFilesSelect = useCallback(
    async (files: File[]) => {
      const newFiles = files.map((file) => ({
        id: `temp-${Date.now()}-${file.name}`,
        name: file.name,
        status: "uploading" as const,
      }));

      setUploadedFiles((prev) => [...prev, ...newFiles]);

      try {
        const result = await uploadMutation.mutateAsync({
          files,
          workflowId: id as string,
        });

        // Update successful files
        setUploadedFiles((prev) =>
          prev.map((f) => {
            const uploadedDoc = result.documents.find(
              (d) => d.document_name === f.name,
            );
            if (uploadedDoc) {
              return { ...f, id: uploadedDoc.id, status: "success" };
            }
            return f;
          }),
        );

        // Update failed files if any
        if (result.failed_uploads.length > 0) {
          setUploadedFiles((prev) =>
            prev.map((f) => {
              const failure = result.failed_uploads.find(
                (fail) => fail.filename === f.name,
              );
              if (failure) {
                return { ...f, status: "error", error: failure.error };
              }
              return f;
            }),
          );
        }
      } catch (error) {
        setUploadedFiles((prev) =>
          prev.map((f) => {
            const isOneOfNewFiles = newFiles.some((nf) => nf.id === f.id);
            if (isOneOfNewFiles) {
              return {
                ...f,
                status: "error",
                error: error instanceof Error ? error.message : "Upload failed",
              };
            }
            return f;
          }),
        );
      }
    },
    [uploadMutation, id],
  );

  const hasSuccessfulUpload = uploadedFiles.some((f) => f.status === "success");
  const isAnyUploading = uploadedFiles.some((f) => f.status === "uploading");

  const handleStartWorkflow = async () => {
    if (!workflow) return;

    try {
      await executeMutation.mutateAsync({
        workflow_name: workflow.workflow_name || "Untitled",
        workflow_definition_id: workflow.definition_id as string,
        workflow_id: workflowId,
        document_ids: uploadedFiles
          .filter((f) => f.status === "success")
          .map((f) => f.id),
        metadata: {},
      });

      setIsStarted(true);
      toast.success("Workflow started successfully");
    } catch (error) {
      console.error("Failed to start workflow:", error);
      toast.error("Failed to start workflow");
    }
  };

  if (isLoadingWorkflow) {
    return (
      <div className="flex items-center justify-center min-h-[200px]">
        <IconLoader2 className="animate-spin size-6 text-primary" />
      </div>
    );
  }

  const definitionName = workflow?.definition_name || "Document Processing";

  const handleViewOutput = (wId: string, dId: string) => {
    setSelectedOutput({ workflowId: wId, documentId: dId });
    setSidebarOpen(true);
    setComparisonSidebarOpen(false);
  };

  const handleViewComparison = (wId: string) => {
    setComparisonSidebarOpen(true);
    setSidebarOpen(false);
  };

  // Determine layout state
  const layoutState = pdfViewerOpen
    ? "pdf-active"
    : sidebarOpen || comparisonSidebarOpen
      ? "two-column"
      : "one-column";

  return (
    <ResizablePanelGroup
      direction="horizontal"
      className="h-svh max-h-svh overflow-hidden"
      key={layoutState}
    >
      <ResizablePanel
        defaultSize={
          layoutState === "pdf-active"
            ? 0
            : layoutState === "two-column"
              ? 50
              : 100
        }
        minSize={layoutState === "pdf-active" ? 0 : 20}
        className={cn(
          "overflow-hidden transition-all duration-300",
          layoutState === "pdf-active" && "max-w-0 opacity-0",
        )}
      >
        <div className="flex flex-col h-full">
          <div className="shrink-0">
            <PageHeader />
          </div>

          <div className="flex-1 overflow-y-auto">
            <div className="p-6">
              <div className="space-y-4 w-full flex justify-center items-center flex-col mb-4">
                <div className="flex items-center gap-3 text-muted-foreground w-full max-w-2xl mx-auto">
                  <div className="bg-[#0232D4]/10 p-1.5 rounded-full ring-1 ring-[#0232D4]/20">
                    <Sparkles className="size-4 text-[#0232D4]/80" />
                  </div>
                  <p className="text-sm font-medium text-zinc-600 dark:text-zinc-400">
                    Welcome to the{" "}
                    <span className="font-bold text-zinc-900 dark:text-zinc-100">
                      {definitionName}
                    </span>{" "}
                    workflow. I&apos;ll guide you through this process.
                  </p>
                </div>
              </div>

              {!isStarted ? (
                <div className="space-y-6 flex flex-col items-center w-full max-w-2xl mx-auto">
                  <FileDropzone
                    onFilesSelect={handleFilesSelect}
                    uploadedFiles={uploadedFiles}
                    isUploading={isAnyUploading}
                    accept={{ "application/pdf": [".pdf"] }}
                    maxFiles={10}
                  />

                  <div className="flex items-center justify-start w-full">
                    {hasSuccessfulUpload && (
                      <Button
                        disabled={isAnyUploading || executeMutation.isPending}
                        onClick={handleStartWorkflow}
                        className="px-8 rounded bg-[#0232D4]/90 text-white hover:bg-[#0232D4]/80"
                      >
                        {executeMutation.isPending ? (
                          <>
                            <IconLoader2 className="size-4 animate-spin mr-2" />
                            Starting...
                          </>
                        ) : (
                          <>
                            <IconPlayerPlay className="size-4 mr-2" />
                            Start Workflow
                          </>
                        )}
                      </Button>
                    )}
                  </div>
                </div>
              ) : (
                /* SSE Timeline Section */
                <div className="w-full">
                  <WorkflowTimeline
                    definitionName={definitionName}
                    events={events}
                    isConnected={isConnected}
                    isComplete={isComplete}
                    onViewOutput={handleViewOutput}
                    onViewComparison={handleViewComparison}
                  />
                </div>
              )}
            </div>
          </div>
        </div>
      </ResizablePanel>

      {sidebarOpen && (
        <>
          <ResizableHandle
            withHandle
            className={cn(layoutState === "pdf-active" && "hidden")}
          />
          <ResizablePanel
            defaultSize={50}
            minSize={20}
            className="overflow-hidden"
          >
            <ExtractionOutputSidebar
              open={sidebarOpen}
              onOpenChange={setSidebarOpen}
              workflowId={selectedOutput?.workflowId ?? null}
              documentId={selectedOutput?.documentId ?? null}
            />
          </ResizablePanel>
        </>
      )}

      {comparisonSidebarOpen && (
        <>
          <ResizableHandle
            withHandle
            className={cn(layoutState === "pdf-active" && "hidden")}
          />
          <ResizablePanel
            defaultSize={50}
            minSize={20}
            className="overflow-hidden"
          >
            <ComparisonOutputSidebar
              open={comparisonSidebarOpen}
              onOpenChange={setComparisonSidebarOpen}
              workflowId={workflowId}
            />
          </ResizablePanel>
        </>
      )}

      {pdfViewerOpen && (
        <>
          <ResizableHandle withHandle />
          <ResizablePanel
            defaultSize={50}
            minSize={20}
            className="overflow-hidden"
          >
            <PDFViewerPanel />
          </ResizablePanel>
        </>
      )}
    </ResizablePanelGroup>
  );
}

export default function WorkflowExecutionPage() {
  return (
    <PDFHighlightProvider>
      <WorkflowExecutionContent />
    </PDFHighlightProvider>
  );
}
