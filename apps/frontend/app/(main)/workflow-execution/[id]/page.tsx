"use client";

import { useState, useCallback, useEffect } from "react";
import { useParams } from "next/navigation";
import { useWorkflowById } from "@/hooks/use-workflows";
import { useUploadDocument, useDocuments } from "@/hooks/use-documents";
import { FileDropzone, type UploadedFile } from "@/components/custom/file-dropzone";
import { Button } from "@/components/ui/button";
import { IconLoader2, IconPlayerPlay, IconCircleCheck } from "@tabler/icons-react";

export default function WorkflowExecutionPage() {
  const { id } = useParams();
  const workflowId = id as string;

  const { data: workflow, isLoading: isLoadingWorkflow } = useWorkflowById(workflowId);
  const { data: existingDocuments, isLoading: isLoadingDocuments } = useDocuments(workflowId);
  const uploadMutation = useUploadDocument();

  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
  const [isStarting, setIsStarting] = useState(false);

  // Sync existing documents to local state
  useEffect(() => {
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
  }, [existingDocuments]);

  const handleFilesSelect = useCallback(
    async (files: File[]) => {
      const newFiles = files.map((file) => ({
        id: `temp-${Date.now()}-${file.name}`,
        name: file.name,
        status: "uploading" as const,
      }));

      setUploadedFiles((prev) => [...prev, ...newFiles]);

      try {
        const result = await uploadMutation.mutateAsync({ files, workflowId: id as string });
        
        // Update successful files
        setUploadedFiles((prev) =>
          prev.map((f) => {
            const uploadedDoc = result.documents.find((d) => d.document_name === f.name);
            if (uploadedDoc) {
              return { ...f, id: uploadedDoc.id, status: "success" };
            }
            return f;
          })
        );

        // Update failed files if any
        if (result.failed_uploads.length > 0) {
          setUploadedFiles((prev) =>
            prev.map((f) => {
              const failure = result.failed_uploads.find((fail) => fail.filename === f.name);
              if (failure) {
                return { ...f, status: "error", error: failure.error };
              }
              return f;
            })
          );
        }
      } catch (error) {
        setUploadedFiles((prev) =>
          prev.map((f) => {
            const isOneOfNewFiles = newFiles.some((nf) => nf.id === f.id);
            if (isOneOfNewFiles) {
              return { ...f, status: "error", error: error instanceof Error ? error.message : "Upload failed" };
            }
            return f;
          })
        );
      }
    },
    [uploadMutation]
  );

  const hasSuccessfulUpload = uploadedFiles.some((f) => f.status === "success");
  const isAnyUploading = uploadedFiles.some((f) => f.status === "uploading");

  const handleStartWorkflow = async () => {
    setIsStarting(true);
    // TODO: Implement workflow execution logic
    await new Promise((resolve) => setTimeout(resolve, 1000));
    setIsStarting(false);
  };

  if (isLoadingWorkflow) {
    return (
      <div className="flex items-center justify-center min-h-[200px]">
        <IconLoader2 className="animate-spin size-6 text-primary" />
      </div>
    );
  }

  const definitionName = workflow?.definition_name || "Document Processing";

  return (
    <div className="flex flex-col p-6">
      {/* Upper Section - Upload Area */}
      <div className="space-y-4 w-full flex justify-center items-center flex-col">
        {/* Welcome Text - Single Line */}
        <div className="flex items-center gap-2 text-muted-foreground">
          <IconCircleCheck className="size-5 text-amber-500" />
          <p className="text-sm">
            Welcome to the <span className="font-medium text-foreground">{definitionName}</span> workflow. I&apos;ll guide you through this process.
          </p>
        </div>

        {/* Upload Widget */}
        <FileDropzone
          onFilesSelect={handleFilesSelect}
          uploadedFiles={uploadedFiles}
          isUploading={isAnyUploading}
          accept={{ "application/pdf": [".pdf"] }}
          maxFiles={10}
        />

        {/* Start Button - Only visible after successful upload */}
        {hasSuccessfulUpload && (
          <Button
            disabled={isAnyUploading || isStarting}
            onClick={handleStartWorkflow}
          >
            {isStarting ? (
              <>
                <IconLoader2 className="size-4 animate-spin" />
                Starting...
              </>
            ) : (
              <>
                <IconPlayerPlay className="size-4" />
                Start Workflow
              </>
            )}
          </Button>
        )}
      </div>

      {/* Lower Section - Workflow Execution View (placeholder) */}
      <div className="mt-8">
        {/* Real-time workflow execution will be displayed here */}
      </div>
    </div>
  );
}
