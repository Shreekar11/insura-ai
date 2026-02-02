"use client";

import React, { useState, useEffect } from "react";
import { Viewer, Worker } from "@react-pdf-viewer/core";
import { Citation, PageDimensions } from "@/types/citation";
import { PDFHighlightLayer } from "./PDFHighlightLayer";
import "@react-pdf-viewer/core/lib/styles/index.css";

interface PDFViewerProps {
  pdfUrl: string;
  citation: Citation | null;
  pageDimensions: Record<number, PageDimensions>;
  onPageChange?: (page: number) => void;
  onScaleChange?: (scale: number) => void;
}

export function PDFViewer({
  pdfUrl,
  citation,
  pageDimensions,
  onPageChange,
  onScaleChange,
}: PDFViewerProps) {
  const [currentPage, setCurrentPage] = useState(1);
  const [scale, setScale] = useState(1);

  // Navigate to primary page when citation changes
  useEffect(() => {
    if (citation?.primaryPage) {
      setCurrentPage(citation.primaryPage);
    }
  }, [citation?.primaryPage]);

  const handlePageChange = (e: any) => {
    const newPage = e.currentPage + 1; // pdfjs uses 0-indexed pages
    setCurrentPage(newPage);
    onPageChange?.(newPage);
  };

  const handleZoomChange = (e: any) => {
    setScale(e.scale);
    onScaleChange?.(e.scale);
  };

  return (
    <div className="relative h-full w-full bg-zinc-100 dark:bg-zinc-900">
      <Worker workerUrl="https://unpkg.com/pdfjs-dist@3.11.174/build/pdf.worker.min.js">
        <div className="relative h-full">
          <Viewer
            fileUrl={pdfUrl}
            defaultScale={1}
            onPageChange={handlePageChange}
            onZoom={handleZoomChange}
            renderPage={(props) => (
              <>
                {props.canvasLayer.children}
                <div className="relative">
                  {props.textLayer.children}
                  {citation && (
                    <PDFHighlightLayer
                      spans={citation.spans}
                      currentPage={currentPage}
                      scale={scale}
                      pageDimensions={pageDimensions}
                    />
                  )}
                  {props.annotationLayer.children}
                </div>
              </>
            )}
          />
        </div>
      </Worker>
    </div>
  );
}
