"use client";

import { Loader2 } from "lucide-react";
import { PDFViewer } from "./pdf-viewer";
import { PDFToolbar } from "./pdf-toolbar";
import { usePDFHighlight } from "@/contexts/pdf-highlight-context";
import { PageDimensions } from "@/types/citation";

interface PDFViewerPanelProps {
  pageDimensions?: Record<number, PageDimensions>;
}

export function PDFViewerPanel({
  pageDimensions: propsDimensions,
}: PDFViewerPanelProps) {
  const {
    pdfUrl,
    activeCitation,
    clearHighlight,
    pageDimensions: contextDimensions,
  } = usePDFHighlight();
  // Use props dimensions if provided, otherwise use context dimensions
  const pageDimensions = propsDimensions ?? contextDimensions;

  if (!pdfUrl) {
    return (
      <div className="flex items-center justify-center h-full bg-white dark:bg-zinc-950">
        <div className="text-center">
          <Loader2 className="size-8 animate-spin text-zinc-400 mx-auto mb-2" />
          <p className="text-sm text-zinc-500">Loading PDF...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-white dark:bg-zinc-950">
      <PDFToolbar onClose={clearHighlight} />
      <div className="flex-1 overflow-hidden">
        <PDFViewer
          pdfUrl={pdfUrl}
          citation={activeCitation}
          pageDimensions={pageDimensions}
        />
      </div>
    </div>
  );
}
