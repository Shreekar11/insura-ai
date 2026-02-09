/**
 * Represents a bounding box in PDF coordinate space.
 *
 * Coordinates use the PDF standard coordinate system where:
 * - Origin (0,0) is at the bottom-left corner of the page
 * - x0, y0: bottom-left corner of the box
 * - x1, y1: top-right corner of the box
 * - All values are in points (1/72 inch)
 *
 * Constraints:
 * - x0 < x1 (left edge is less than right edge)
 * - y0 < y1 (bottom edge is less than top edge)
 */
export interface BoundingBox {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

/**
 * Represents a continuous span of text on a single page with its location.
 *
 * A citation may span multiple pages, so an array of CitationSpans is used
 * to represent the complete citation with one span per page.
 */
export interface CitationSpan {
  pageNumber: number;
  boundingBoxes: BoundingBox[];
  textContent: string;
}

/**
 * Type of source document or clause that the citation references.
 */
export type SourceType = "effective_coverage" | "effective_exclusion" | "endorsement" | "condition" | "clause";

/**
 * Method used to extract the citation from the PDF.
 */
export type ExtractionMethod = "docling" | "pdfplumber" | "manual";

/**
 * How the citation coordinates were resolved.
 */
export type ResolutionMethod = "direct_text_match" | "semantic_chunk_match" | "placeholder";

/**
 * Represents a range of pages in a document.
 */
export interface PageRange {
  start: number;
  end: number;
}

/**
 * Represents a citation with its location, content, and metadata.
 *
 * A citation links extracted insurance policy content (coverages, exclusions, etc.)
 * to its original location in the source PDF document.
 */
export interface Citation {
  /** Unique identifier for this citation */
  id: string;

  /** ID of the source document */
  documentId: string;

  /** Type of the source being cited */
  sourceType: SourceType;

  /** Canonical or stable ID of the source item */
  sourceId: string;

  /** Array of spans representing the citation across one or more pages */
  spans: CitationSpan[];

  /** The complete verbatim text from the source document */
  verbatimText: string;

  /** Primary page number where the citation appears */
  primaryPage: number;

  /** Optional range of pages if citation spans multiple pages */
  pageRange?: PageRange;

  /** Optional confidence score for the extraction (0-1) */
  extractionConfidence?: number;

  /** Optional method used to extract this citation */
  extractionMethod?: ExtractionMethod;

  /** Optional reference to a specific clause (e.g., "2.3.1") */
  clauseReference?: string;

  /** How the citation was resolved (direct text match, semantic chunk search, or placeholder) */
  resolutionMethod?: ResolutionMethod;
}

/**
 * Represents the physical dimensions of a PDF page.
 *
 * Dimensions are in points (1/72 inch) following PDF standards.
 */
export interface PageDimensions {
  pageNumber: number;
  widthPoints: number;
  heightPoints: number;
  /** Rotation of the page in degrees (0, 90, 180, or 270) */
  rotation: number;
}

/**
 * Response structure for fetching citations with their associated page dimensions.
 */
export interface CitationsResponse {
  citations: Citation[];
  pageDimensions: Record<number, PageDimensions>;
}
