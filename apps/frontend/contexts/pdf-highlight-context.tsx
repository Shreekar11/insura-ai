"use client";

import React, { createContext, useContext, useState, useCallback } from "react";
import { Citation, PageDimensions } from "@/types/citation";

interface PDFHighlightContextValue {
  // Panel visibility
  pdfViewerOpen: boolean;
  setPdfViewerOpen: (open: boolean) => void;

  // Active citation
  activeCitation: Citation | null;
  setActiveCitation: (citation: Citation | null) => void;

  // PDF document URL
  pdfUrl: string | null;
  setPdfUrl: (url: string | null) => void;

  // Page dimensions for coordinate transformation
  pageDimensions: Record<number, PageDimensions>;
  setPageDimensions: (dims: Record<number, PageDimensions>) => void;

  // Helper to trigger highlight
  highlightCitation: (citation: Citation, pdfUrl: string, pageDimensions?: Record<number, PageDimensions>) => void;

  // Helper to clear highlight
  clearHighlight: () => void;
}

const PDFHighlightContext = createContext<PDFHighlightContextValue | undefined>(
  undefined
);

export function PDFHighlightProvider({ children }: { children: React.ReactNode }) {
  const [pdfViewerOpen, setPdfViewerOpen] = useState(false);
  const [activeCitation, setActiveCitation] = useState<Citation | null>(null);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pageDimensions, setPageDimensions] = useState<Record<number, PageDimensions>>({});

  const highlightCitation = useCallback((citation: Citation, url: string, dims?: Record<number, PageDimensions>) => {
    setActiveCitation(citation);
    setPdfUrl(url);
    if (dims) {
      setPageDimensions(dims);
    }
    setPdfViewerOpen(true);
  }, []);

  const clearHighlight = useCallback(() => {
    setActiveCitation(null);
    setPdfViewerOpen(false);
  }, []);

  return (
    <PDFHighlightContext.Provider
      value={{
        pdfViewerOpen,
        setPdfViewerOpen,
        activeCitation,
        setActiveCitation,
        pdfUrl,
        setPdfUrl,
        pageDimensions,
        setPageDimensions,
        highlightCitation,
        clearHighlight,
      }}
    >
      {children}
    </PDFHighlightContext.Provider>
  );
}

export function usePDFHighlight() {
  const context = useContext(PDFHighlightContext);
  if (context === undefined) {
    throw new Error("usePDFHighlight must be used within PDFHighlightProvider");
  }
  return context;
}
