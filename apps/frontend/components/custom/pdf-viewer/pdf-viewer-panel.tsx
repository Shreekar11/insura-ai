"use client";

import { Loader2 } from "lucide-react";
import { PDFViewer } from "./pdf-viewer";
import { PDFToolbar } from "./pdf-toolbar";
import { usePDFHighlight } from "@/contexts/pdf-highlight-context";
import { useDocumentUrl } from "@/hooks/use-documents";
import { PageDimensions } from "@/types/citation";

interface PDFViewerPanelProps {
  pageDimensions?: Record<number, PageDimensions>;
}

export function PDFViewerPanel({
  pageDimensions: propsDimensions,
}: PDFViewerPanelProps) {
  const {
    documentId,
    activeCitation,
    clearHighlight,
    pageDimensions: contextDimensions,
  } = usePDFHighlight();

  // Fetch the signed URL for the document
  const { data: urlData, isLoading: isLoadingUrl } = useDocumentUrl(
    documentId || undefined,
  );

  // Use props dimensions if provided, otherwise use context dimensions
  const pageDimensions = propsDimensions ?? contextDimensions;

  if (!documentId) {
    return null;
  }

  if (isLoadingUrl) {
    return (
      <div className="flex items-center justify-center h-full bg-white dark:bg-zinc-950">
        <div className="text-center">
          <Loader2 className="size-8 animate-spin text-zinc-400 mx-auto mb-2" />
          <p className="text-sm text-zinc-500">Loading document...</p>
        </div>
      </div>
    );
  }

  if (!urlData?.url) {
    return (
      <div className="flex items-center justify-center h-full bg-white dark:bg-zinc-950">
        <div className="text-center p-6">
          <div className="bg-red-50 dark:bg-red-900/10 p-3 rounded-full mb-4 inline-block">
            <Loader2 className="size-6 text-red-500" />
          </div>
          <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
            Failed to load PDF
          </p>
          <p className="text-xs text-zinc-500 mt-1">
            Could not retrieve a secure access URL for this document.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-white dark:bg-zinc-950">
      <PDFToolbar onClose={clearHighlight} />
      <div className="flex-1 overflow-hidden">
        <PDFViewer
          pdfUrl={urlData.url}
          citation={activeCitation}
          pageDimensions={pageDimensions}
        />
      </div>
    </div>
  );
}
