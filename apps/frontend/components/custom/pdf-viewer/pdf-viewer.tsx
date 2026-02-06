"use client";

import { useState, useEffect, useMemo, useRef } from "react";
import { Viewer, Worker } from "@react-pdf-viewer/core";
import { pageNavigationPlugin } from "@react-pdf-viewer/page-navigation";
import { Citation, PageDimensions } from "@/types/citation";
import { PDFHighlightLayer } from "./pdf-highlight-layer";
import "@react-pdf-viewer/core/lib/styles/index.css";

interface PDFViewerProps {
  pdfUrl: string;
  citation: Citation | null;
  pageDimensions: Record<number, PageDimensions>;
}

export function PDFViewer({
  pdfUrl,
  citation,
  pageDimensions,
}: PDFViewerProps) {
  const [currentPage, setCurrentPage] = useState(1);
  const [scale, setScale] = useState(1);
  const documentLoaded = useRef(false);

  const pageNavigationPluginInstance = useMemo(
    () => pageNavigationPlugin(),
    [],
  );
  const { jumpToPage } = pageNavigationPluginInstance;

  // Auto-scroll to the citation's page when citation changes
  useEffect(() => {
    if (citation?.primaryPage && documentLoaded.current) {
      const targetPage = citation.primaryPage - 1; // 0-indexed
      jumpToPage(targetPage);
      setCurrentPage(citation.primaryPage);
    }
  }, [citation?.primaryPage, citation?.id, jumpToPage]);

  const handleDocumentLoad = () => {
    documentLoaded.current = true;
    // Jump to citation page after initial load
    if (citation?.primaryPage) {
      jumpToPage(citation.primaryPage - 1);
      setCurrentPage(citation.primaryPage);
    }
  };

  const handlePageChange = (e: any) => {
    const newPage = e.currentPage + 1; // pdfjs uses 0-indexed pages
    setCurrentPage(newPage);
  };

  const handleZoomChange = (e: any) => {
    setScale(e.scale);
  };

  return (
    <div className="relative h-full w-full bg-zinc-100 dark:bg-zinc-900">
      <Worker workerUrl="https://unpkg.com/pdfjs-dist@3.11.174/build/pdf.worker.min.js">
        <div className="relative h-full">
          <Viewer
            fileUrl={pdfUrl}
            defaultScale={1}
            initialPage={
              citation?.primaryPage ? citation.primaryPage - 1 : 0
            }
            plugins={[pageNavigationPluginInstance]}
            onDocumentLoad={handleDocumentLoad}
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
