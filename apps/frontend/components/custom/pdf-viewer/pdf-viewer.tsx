"use client";

import { useState, useEffect, useRef, useMemo } from "react";
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
  const manualScroll = useRef(false);
  const lastJumpedCitationId = useRef<string | null>(null);

  const pageNavigationPluginInstance = pageNavigationPlugin();
  const { jumpToPage } = pageNavigationPluginInstance;

  // Auto-scroll to the citation's page and bounding box when citation changes
  useEffect(() => {
    if (
      citation?.id &&
      citation.id !== lastJumpedCitationId.current &&
      citation.primaryPage &&
      documentLoaded.current
    ) {
      const pageIndex = citation.primaryPage - 1;
      const pageHeight = pageDimensions[citation.primaryPage]?.heightPoints;

      // Find the first bounding box on the primary page to scroll to
      const primaryPageSpan = citation.spans.find(
        (s) => s.pageNumber === citation.primaryPage,
      );
      const firstBox = primaryPageSpan?.boundingBoxes?.[0];

      lastJumpedCitationId.current = citation.id;

      const isFullPage =
        !firstBox ||
        (firstBox.x0 === 0 &&
          firstBox.y0 === 0 &&
          firstBox.x1 >= 611 &&
          firstBox.y1 >= 791);

      if (!isFullPage && firstBox && pageHeight) {
        const topFromTop = pageHeight - firstBox.y1;
        const left = firstBox.x0;
        const scrollOffset = Math.max(0, topFromTop - 50);
        const destination = [pageIndex, "XYZ", left, scrollOffset, null];
        (pageNavigationPluginInstance as any).jumpToDestination(destination);
      } else {
        jumpToPage(pageIndex);
      }

      setCurrentPage(citation.primaryPage);
    }
  }, [citation, jumpToPage, pageDimensions, pageNavigationPluginInstance]);

  const handleDocumentLoad = () => {
    documentLoaded.current = true;
  };

  const handlePageChange = (e: any) => {
    const newPage = e.currentPage + 1;
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
            initialPage={citation?.primaryPage ? citation.primaryPage - 1 : 0}
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
                      pageNumber={props.pageIndex + 1}
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
