/**
 * Transform functions for converting between API types (snake_case) and
 * frontend types (camelCase) for the citations feature.
 */

import type {
  Citation as ApiCitation,
  CitationSpan as ApiCitationSpan,
  CitationsResponse as ApiCitationsResponse,
  PageDimensions as ApiPageDimensions,
  BoundingBox as ApiBoundingBox,
} from "@/schema/generated/citations";

import type {
  Citation,
  CitationSpan,
  CitationsResponse,
  PageDimensions,
  BoundingBox,
  SourceType,
  ExtractionMethod,
  ResolutionMethod,
} from "@/types/citation";

/**
 * Transform API BoundingBox to frontend BoundingBox.
 * Note: BoundingBox fields are the same (x0, y0, x1, y1), so this is identity.
 */
export function transformBoundingBox(apiBbox: ApiBoundingBox): BoundingBox {
  return {
    x0: apiBbox.x0,
    y0: apiBbox.y0,
    x1: apiBbox.x1,
    y1: apiBbox.y1,
  };
}

/**
 * Transform API CitationSpan to frontend CitationSpan.
 * Converts snake_case to camelCase.
 */
export function transformCitationSpan(apiSpan: ApiCitationSpan): CitationSpan {
  return {
    pageNumber: apiSpan.page_number,
    boundingBoxes: apiSpan.bounding_boxes.map(transformBoundingBox),
    textContent: apiSpan.text_content,
  };
}

/**
 * Transform API Citation to frontend Citation.
 * Converts all snake_case fields to camelCase.
 */
export function transformCitation(apiCitation: ApiCitation): Citation {
  return {
    id: apiCitation.id,
    documentId: apiCitation.document_id,
    sourceType: apiCitation.source_type as SourceType,
    sourceId: apiCitation.source_id,
    spans: apiCitation.spans.map(transformCitationSpan),
    verbatimText: apiCitation.verbatim_text,
    primaryPage: apiCitation.primary_page,
    pageRange: apiCitation.page_range
      ? {
          start: apiCitation.page_range.start,
          end: apiCitation.page_range.end,
        }
      : undefined,
    extractionConfidence: apiCitation.extraction_confidence ?? undefined,
    extractionMethod: (apiCitation.extraction_method as ExtractionMethod) ?? undefined,
    clauseReference: apiCitation.clause_reference ?? undefined,
    resolutionMethod: (apiCitation.resolution_method as ResolutionMethod) ?? undefined,
  };
}

/**
 * Transform API PageDimensions to frontend PageDimensions.
 * Converts snake_case to camelCase.
 */
export function transformPageDimensions(apiDims: ApiPageDimensions): PageDimensions {
  return {
    pageNumber: apiDims.page_number,
    widthPoints: apiDims.width_points,
    heightPoints: apiDims.height_points,
    rotation: typeof apiDims.rotation === "number" ? apiDims.rotation : 0,
  };
}

/**
 * Transform API CitationsResponse to frontend CitationsResponse.
 * Converts all nested types and the page_dimensions map.
 */
export function transformCitationsResponse(
  apiResponse: ApiCitationsResponse
): CitationsResponse {
  // Transform citations array
  const citations = apiResponse.citations.map(transformCitation);

  // Transform page_dimensions map (string keys to number keys)
  // Defensive guard: page_dimensions may be undefined if backend doesn't return it
  const pageDimensions: Record<number, PageDimensions> = {};
  if (apiResponse.page_dimensions) {
    for (const [key, value] of Object.entries(apiResponse.page_dimensions)) {
      const pageNum = parseInt(key, 10);
      if (!isNaN(pageNum)) {
        pageDimensions[pageNum] = transformPageDimensions(value);
      }
    }
  }

  return {
    citations,
    pageDimensions,
  };
}
