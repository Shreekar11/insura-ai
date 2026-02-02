"use client";

import React from "react";
import { Button } from "@/components/ui/button";
import { ZoomIn, ZoomOut, ChevronLeft, ChevronRight, X } from "lucide-react";

interface PDFToolbarProps {
  currentPage: number;
  totalPages: number;
  scale: number;
  onPageChange: (page: number) => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onClose: () => void;
}

export function PDFToolbar({
  currentPage,
  totalPages,
  scale,
  onPageChange,
  onZoomIn,
  onZoomOut,
  onClose,
}: PDFToolbarProps) {
  const canGoPrevious = currentPage > 1;
  const canGoNext = currentPage < totalPages;

  return (
    <div className="flex items-center justify-between px-4 py-2 border-b border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900/50">
      <div className="flex items-center gap-2">
        {/* Page navigation */}
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          onClick={() => onPageChange(currentPage - 1)}
          disabled={!canGoPrevious}
        >
          <ChevronLeft className="size-4" />
        </Button>
        <span className="text-xs text-zinc-600 dark:text-zinc-400 min-w-[80px] text-center">
          Page {currentPage} / {totalPages}
        </span>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          onClick={() => onPageChange(currentPage + 1)}
          disabled={!canGoNext}
        >
          <ChevronRight className="size-4" />
        </Button>
      </div>

      <div className="flex items-center gap-2">
        {/* Zoom controls */}
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          onClick={onZoomOut}
        >
          <ZoomOut className="size-4" />
        </Button>
        <span className="text-xs text-zinc-600 dark:text-zinc-400 min-w-[50px] text-center">
          {Math.round(scale * 100)}%
        </span>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          onClick={onZoomIn}
        >
          <ZoomIn className="size-4" />
        </Button>

        {/* Close button */}
        <div className="ml-2 pl-2 border-l border-zinc-200 dark:border-zinc-800">
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 rounded-full"
            onClick={onClose}
          >
            <X className="size-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
