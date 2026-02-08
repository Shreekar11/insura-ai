"use client";

import { useState, useEffect, useRef, useMemo } from "react";
import {
  Viewer,
  Worker,
  Plugin,
  PluginFunctions,
  Destination,
} from "@react-pdf-viewer/core";
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
  const jumpToDestinationRef = useRef<(destination: Destination) => void>(null);
  const pageNavigationPluginInstance = pageNavigationPlugin();
  const { jumpToPage } = pageNavigationPluginInstance;

  const jumpPlugin = useMemo(
    (): Plugin => ({
      install: (pluginFunctions: PluginFunctions) => {
        (jumpToDestinationRef as any).current =
          pluginFunctions.jumpToDestination;
      },
    }),
    [],
  );

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
        // Correct calculation: zoom to XYZ where Y is distance from bottom.
        // We want the box to be at the top of the viewport (with padding).
        // Since Y=0 is bottom, top of box is firstBox.y1.
        // Adding 50 points of padding above it.
        const bottomOffset = Math.min(pageHeight, firstBox.y1 + 50);
        const leftOffset = firstBox.x0;

        if (jumpToDestinationRef.current) {
          jumpToDestinationRef.current({
            pageIndex,
            bottomOffset,
            leftOffset,
            scaleTo: scale,
          });
        }
      } else {
        jumpToPage(pageIndex);
      }

      setCurrentPage(citation.primaryPage);
    }
  }, [citation, jumpToPage, pageDimensions, scale]);

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
            plugins={[pageNavigationPluginInstance, jumpPlugin]}
            onDocumentLoad={handleDocumentLoad}
            onPageChange={handlePageChange}
            onZoom={handleZoomChange}
            renderPage={(props) => (
              <>
                {props.canvasLayer.children}
                {props.textLayer.children}
                {citation && (
                  <PDFHighlightLayer
                    spans={citation.spans}
                    pageNumber={props.pageIndex + 1}
                    scale={props.scale}
                    pageDimensions={pageDimensions}
                  />
                )}
                {props.annotationLayer.children}
              </>
            )}
          />
        </div>
      </Worker>
    </div>
  );
}
