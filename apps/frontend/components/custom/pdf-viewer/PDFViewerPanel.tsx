"use client";

import React, { useState } from "react";
import { Loader2 } from "lucide-react";
import { PDFViewer } from "./PDFViewer";
import { PDFToolbar } from "./PDFToolbar";
import { usePDFHighlight } from "@/contexts/pdf-highlight-context";
import { PageDimensions } from "@/types/citation";

interface PDFViewerPanelProps {
  pageDimensions: Record<number, PageDimensions>;
}

export function PDFViewerPanel({ pageDimensions }: PDFViewerPanelProps) {
  const { pdfUrl, activeCitation, clearHighlight } = usePDFHighlight();
  const [currentPage, setCurrentPage] = useState(1);
  const [scale, setScale] = useState(1);
  const [totalPages, setTotalPages] = useState(0);

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

  const handleZoomIn = () => {
    setScale((prev) => Math.min(prev + 0.25, 3));
  };

  const handleZoomOut = () => {
    setScale((prev) => Math.max(prev - 0.25, 0.5));
  };

  return (
    <div className="flex flex-col h-full bg-white dark:bg-zinc-950 border-l border-zinc-200 dark:border-zinc-800">
      <PDFToolbar
        currentPage={currentPage}
        totalPages={totalPages || 1}
        scale={scale}
        onPageChange={setCurrentPage}
        onZoomIn={handleZoomIn}
        onZoomOut={handleZoomOut}
        onClose={clearHighlight}
      />
      <div className="flex-1 overflow-hidden">
        <PDFViewer
          pdfUrl={pdfUrl}
          citation={activeCitation}
          pageDimensions={pageDimensions}
          onPageChange={setCurrentPage}
          onScaleChange={setScale}
        />
      </div>
    </div>
  );
}
