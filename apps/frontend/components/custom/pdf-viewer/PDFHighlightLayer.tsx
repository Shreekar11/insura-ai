"use client";

import React from "react";
import { CitationSpan, PageDimensions } from "@/types/citation";
import { transformPageBoxes } from "@/lib/coordinate-transform";

interface PDFHighlightLayerProps {
  spans: CitationSpan[];
  currentPage: number;
  scale: number;
  pageDimensions: Record<number, PageDimensions>;
}

export function PDFHighlightLayer({
  spans,
  currentPage,
  scale,
  pageDimensions,
}: PDFHighlightLayerProps) {
  // Filter spans for current page
  const currentPageSpans = spans.filter((s) => s.pageNumber === currentPage);

  if (currentPageSpans.length === 0) {
    return null;
  }

  const pageHeight = pageDimensions[currentPage]?.heightPoints;
  if (!pageHeight) {
    return null;
  }

  return (
    <div className="absolute inset-0 pointer-events-none z-10">
      {currentPageSpans.map((span, spanIdx) => {
        const viewerBoxes = transformPageBoxes(
          span.boundingBoxes,
          pageHeight,
          scale
        );

        return (
          <React.Fragment key={spanIdx}>
            {viewerBoxes.map((box, boxIdx) => (
              <div
                key={`${spanIdx}-${boxIdx}`}
                className="absolute bg-amber-400/30 dark:bg-amber-500/30 border border-amber-500/50 dark:border-amber-400/50"
                style={{
                  left: `${box.left}px`,
                  top: `${box.top}px`,
                  width: `${box.width}px`,
                  height: `${box.height}px`,
                }}
              />
            ))}
          </React.Fragment>
        );
      })}
    </div>
  );
}
