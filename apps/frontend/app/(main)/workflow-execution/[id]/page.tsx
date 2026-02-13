"use client";

import { useState, useCallback, useEffect, useMemo, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import dynamic from "next/dynamic";
import { useParams } from "next/navigation";
import { useWorkflowById, useExecuteWorkflow } from "@/hooks/use-workflows";
import { useUploadDocument, useDocuments } from "@/hooks/use-documents";
import {
  FileDropzone,
  type UploadedFile,
} from "@/components/custom/file-dropzone";
import { Button } from "@/components/ui/button";
import { IconLoader2, IconPlayerPlay } from "@tabler/icons-react";
import { Sparkles, Loader2, Copy, Check, ArrowDown } from "lucide-react";
import { useWorkflowStream } from "@/hooks/use-workflow-stream";
import { WorkflowTimeline } from "@/components/custom/workflow-timeline";
import { toast } from "sonner";
import { useActiveWorkflow } from "@/contexts/active-workflow-context";
import { cn } from "@/lib/utils";
import { ChatInterface } from "@/components/custom/chat-interface";
import { useChat } from "@/hooks/use-chat";
import { useChatMessages } from "@/hooks/use-chat-messages";
import { useTypewriter } from "@/hooks/use-typewriter";
import type {
  GraphRAGResponse,
  MentionedDocument,
} from "@/schema/generated/query";

import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { PageHeader } from "@/components/layout/page-header";
import {
  PDFHighlightProvider,
  usePDFHighlight,
} from "@/contexts/pdf-highlight-context";
import { Input } from "@/components/ui/input";
const ExtractionOutputSidebar = dynamic(
  () =>
    import("@/components/custom/extraction-output-sidebar").then(
      (m) => m.ExtractionOutputSidebar,
    ),
  {
    loading: () => (
      <div className="h-full flex items-center justify-center bg-white dark:bg-zinc-950">
        <IconLoader2 className="animate-spin size-6" />
      </div>
    ),
  },
);

const ComparisonOutputSidebar = dynamic(
  () =>
    import("@/components/custom/comparison-output-sidebar").then(
      (m) => m.ComparisonOutputSidebar,
    ),
  {
    loading: () => (
      <div className="h-full flex items-center justify-center bg-white dark:bg-zinc-950">
        <IconLoader2 className="animate-spin size-6" />
      </div>
    ),
  },
);

const ProposalOutputSidebar = dynamic(
  () =>
    import("@/components/custom/proposal-output-sidebar").then(
      (m) => m.ProposalOutputSidebar,
    ),
  {
    loading: () => (
      <div className="h-full flex items-center justify-center bg-white dark:bg-zinc-950">
        <IconLoader2 className="animate-spin size-6" />
      </div>
    ),
  },
);

const PDFViewerPanel = dynamic(
  () =>
    import("@/components/custom/pdf-viewer/pdf-viewer-panel").then(
      (m) => m.PDFViewerPanel,
    ),
  {
    loading: () => (
      <div className="h-full flex items-center justify-center bg-white dark:bg-zinc-950">
        <IconLoader2 className="animate-spin size-6" />
      </div>
    ),
  },
);

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      toast.success("Copied to clipboard");
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      toast.error("Failed to copy");
    }
  };

  return (
    <Button
      variant="ghost"
      size="icon"
      className="size-7 text-zinc-400 rounded-sm hover:text-zinc-600 dark:hover:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800"
      onClick={handleCopy}
    >
      {copied ? (
        <Check className="size-3.5 text-emerald-500" />
      ) : (
        <Copy className="size-3.5" />
      )}
    </Button>
  );
}

function MessageBubble({
  msg,
  onScrollToBottom,
}: {
  msg: {
    query: string;
    answer: string | null;
    created_at: string;
    isNew: boolean;
  };
  onScrollToBottom: () => void;
}) {
  const { displayedText, isTyping } = useTypewriter(msg.answer, msg.isNew);

  // Auto-scroll while typing
  useEffect(() => {
    if (isTyping) {
      onScrollToBottom();
    }
  }, [displayedText, isTyping, onScrollToBottom]);

  return (
    <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
      {/* User Query */}
      <div className="flex justify-end group">
        <div className="flex flex-col items-end gap-1 max-w-[80%]">
          <div className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded px-4 py-2">
            <p className="text-sm text-zinc-800 dark:text-zinc-200">
              {msg.query}
            </p>
          </div>
          <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
            <span className="text-xs text-zinc-500 dark:text-zinc-400">
              {msg.created_at &&
                new Date(msg.created_at).toLocaleTimeString("en-US", {
                  hour: "numeric",
                  minute: "2-digit",
                  hour12: true,
                })}
            </span>
            <CopyButton text={msg.query} />
          </div>
        </div>
      </div>

      {/* LLM Response */}
      <div className="flex justify-start gap-3">
        <div className="shrink-0">
          {!msg.answer || isTyping ? (
            <div className="bg-[#0232D4]/10 p-1 rounded-full ring-1 ring-[#0232D4]/20 flex items-center justify-center">
              {!msg.answer ? (
                <Loader2 className="size-4 text-[#0232D4]/80 animate-spin stroke-[3]" />
              ) : (
                <Sparkles className="size-4 text-[#0232D4]/80" />
              )}
            </div>
          ) : (
            <div className="bg-[#0232D4]/10 p-1 rounded-full ring-1 ring-[#0232D4]/20">
              <Sparkles className="size-4 text-[#0232D4]/80" />
            </div>
          )}
        </div>
        <div className="max-w-full w-full group">
          {!msg.answer ? (
            <div className="flex items-center gap-2 text-zinc-500 italic text-sm py-0.5">
              Thinking...
            </div>
          ) : (
            <div className="flex flex-col gap-1">
              <div className="prose-custom [&>*:first-child]:mt-0 max-w-none text-zinc-800 dark:text-zinc-200 min-h-[1.5em]">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {displayedText}
                </ReactMarkdown>
                {isTyping && (
                  <span className="inline-block w-1.5 h-4 ml-0.5 align-middle bg-zinc-400 animate-pulse" />
                )}
              </div>
              <div className="opacity-0 group-hover:opacity-100 transition-opacity">
                <CopyButton text={msg.answer} />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

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
  const [messages, setMessages] = useState<
    {
      query: string;
      answer: string | null;
      created_at: string;
      isNew: boolean;
    }[]
  >([]);
  const [showBlurOverlay, setShowBlurOverlay] = useState(false);
  const [showScrollButton, setShowScrollButton] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);

  const chatMutation = useChat(workflowId);

  // Scroll logic
  const scrollToBottom = useCallback(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({
        top: scrollRef.current.scrollHeight,
        behavior: "smooth",
      });
    }
  }, []);

  // Sidebar states
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [comparisonSidebarOpen, setComparisonSidebarOpen] = useState(false);
  const [proposalSidebarOpen, setProposalSidebarOpen] = useState(false);
  const [selectedOutput, setSelectedOutput] = useState<{
    workflowId: string;
    documentId: string;
    type?: "extraction" | "comparison" | "proposal";
  } | null>(null);

  // SSE Stream
  const { events, isConnected, isComplete } = useWorkflowStream(
    isStarted ? workflowId : null,
  );

  useEffect(() => {
    const scrollContainer = scrollRef.current;
    if (!scrollContainer) return;

    const handleScroll = () => {
      const { scrollTop, scrollHeight, clientHeight } = scrollContainer;
      // Show button if we are more than 100px from the bottom
      const isAtBottom = scrollHeight - scrollTop - clientHeight < 100;
      setShowScrollButton(!isAtBottom);
    };

    handleScroll(); // Call once on mount to set initial state

    scrollContainer.addEventListener("scroll", handleScroll);
    return () => scrollContainer.removeEventListener("scroll", handleScroll);
  }, [messages.length, isComplete]); // Re-run when messages change or completion state changes

  // Scroll to bottom when new messages are added or thinking starts
  useEffect(() => {
    if (isComplete) {
      scrollToBottom();
    }
  }, [messages.length, isComplete, scrollToBottom]);

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

  // Load chat history
  const { data: chatHistory } = useChatMessages(workflowId);
  const historyLoadedRef = useRef(false);

  useEffect(() => {
    if (chatHistory && chatHistory.length > 0 && !historyLoadedRef.current) {
      const historyPairs: {
        query: string;
        answer: string | null;
        created_at: string;
        isNew: boolean;
      }[] = [];
      let currentQuery: string | null = null;

      chatHistory.forEach((msg) => {
        if (msg.role === "user") {
          // If there was a pending query without answer, push it
          if (currentQuery) {
            historyPairs.push({
              query: currentQuery,
              answer: null,
              created_at: msg.created_at,
              isNew: false,
            });
          }
          currentQuery = msg.content;
        } else if (msg.role === "model") {
          if (currentQuery) {
            historyPairs.push({
              query: currentQuery,
              answer: msg.content,
              created_at: msg.created_at,
              isNew: false,
            });
            currentQuery = null;
          }
        }
      });

      // Push last pending query
      if (currentQuery) {
        historyPairs.push({
          query: currentQuery,
          answer: null,
          created_at: "",
          isNew: false,
        });
      }

      setMessages((prev) => [...historyPairs, ...prev]);
      historyLoadedRef.current = true;
    }
  }, [chatHistory]);

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

  const hasSuccessfulUpload = useMemo(
    () => uploadedFiles.some((f) => f.status === "success"),
    [uploadedFiles],
  );
  const isAnyUploading = useMemo(
    () => uploadedFiles.some((f) => f.status === "uploading"),
    [uploadedFiles],
  );

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

  const definitionName = workflow?.definition_name || "Document Processing";

  // Determine layout state
  const layoutState = useMemo(
    () =>
      pdfViewerOpen
        ? "pdf-active"
        : sidebarOpen || comparisonSidebarOpen || proposalSidebarOpen
          ? "two-column"
          : "one-column",
    [pdfViewerOpen, sidebarOpen, comparisonSidebarOpen, proposalSidebarOpen],
  );

  if (isLoadingWorkflow) {
    return (
      <div className="flex items-center justify-center min-h-[200px]">
        <IconLoader2 className="animate-spin size-6 text-primary" />
      </div>
    );
  }

  const handleViewOutput = (wId: string, dId: string) => {
    setSelectedOutput({ workflowId: wId, documentId: dId });
    setSidebarOpen(true);
    setComparisonSidebarOpen(false);
  };

  const handleViewComparison = (wId: string) => {
    setComparisonSidebarOpen(true);
    setSidebarOpen(false);
    setProposalSidebarOpen(false);
  };

  const handleViewProposal = (wId: string) => {
    setProposalSidebarOpen(true);
    setSidebarOpen(false);
    setComparisonSidebarOpen(false);
  };

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

          <div className="flex-1 overflow-y-auto" ref={scrollRef}>
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
                <div className="w-full max-w-2xl mx-auto flex flex-col gap-12 pb-48">
                  <WorkflowTimeline
                    definitionName={definitionName}
                    events={events}
                    isConnected={isConnected}
                    isComplete={isComplete}
                    onViewOutput={handleViewOutput}
                    onViewComparison={handleViewComparison}
                    onViewProposal={handleViewProposal}
                  />

                  {isComplete && (
                    <div className="space-y-12">
                      {messages.map((msg, idx) => (
                        <MessageBubble
                          key={idx}
                          msg={msg}
                          onScrollToBottom={scrollToBottom}
                        />
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {isComplete && (
            <div className="relative pb-4">
              {/* Scroll Down Button */}
              {showScrollButton && (
                <div className="absolute -top-12 left-0 right-0 flex justify-center z-40 animate-in fade-in zoom-in duration-200">
                  <Button
                    variant="secondary"
                    size="icon"
                    className="rounded-full text-[#2B2C36] size-9 shadow-lg bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 hover:bg-zinc-50 dark:hover:bg-zinc-800"
                    onClick={scrollToBottom}
                  >
                    <ArrowDown className="size-4" />
                  </Button>
                </div>
              )}

              {/* Global Blur Overlay for content scrolling behind the chat */}
              <div className="absolute -top-16 left-0 right-0 h-16 bg-gradient-to-b from-transparent to-white/90 dark:to-zinc-950/90 pointer-events-none z-20 backdrop-blur-md [mask-image:linear-gradient(to_bottom,transparent,black)]" />

              <div className="shrink-0 bg-white/90 dark:bg-zinc-950/90 px-6 sticky bottom-0 z-30">
                <ChatInterface
                  isLoading={chatMutation.isPending}
                  showBlurOverlay={showBlurOverlay}
                  documents={existingDocuments?.documents ?? []}
                  onAsk={(
                    query: string,
                    mentionedDocs: MentionedDocument[],
                  ) => {
                    setShowBlurOverlay(true);
                    setMessages((prev) => [
                      ...prev,
                      {
                        query,
                        answer: null,
                        created_at: new Date().toISOString(),
                        isNew: true,
                      },
                    ]);
                    chatMutation.mutate(
                      {
                        query,
                        mentioned_documents: mentionedDocs,
                        document_ids: mentionedDocs.map((d) => d.id),
                      },
                      {
                        onSuccess: (data: GraphRAGResponse) => {
                          setShowBlurOverlay(true);
                          setMessages((prev) =>
                            prev.map((m, i) =>
                              i === prev.length - 1
                                ? { ...m, answer: data.answer }
                                : m,
                            ),
                          );
                          setShowBlurOverlay(false);
                        },
                        onError: () => {
                          setMessages((prev) =>
                            prev.map((m, i) =>
                              i === prev.length - 1
                                ? {
                                    ...m,
                                    answer:
                                      "Failed to get response. Please try again.",
                                  }
                                : m,
                            ),
                          );
                        },
                      },
                    );
                  }}
                />
              </div>
              <p className="text-center mt-2 text-xs text-zinc-500">
                AI can make mistakes. Check important info.
              </p>
            </div>
          )}
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

      {proposalSidebarOpen && (
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
            <ProposalOutputSidebar
              open={proposalSidebarOpen}
              onOpenChange={setProposalSidebarOpen}
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
