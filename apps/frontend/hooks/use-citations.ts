import { useQuery } from "@tanstack/react-query";
import { Citation, CitationsResponse } from "@/types/citation";
import { DefaultService } from "@/schema/generated/citations";
import { transformCitationsResponse } from "@/lib/citation-transforms";

/**
 * Hook for lazy-fetching citations for a document in a workflow.
 * Data is only fetched when both workflowId and documentId are provided.
 */
export const useCitations = (
  workflowId: string | null,
  documentId: string | null
) => {
  return useQuery<CitationsResponse | null>({
    queryKey: ["citations", workflowId, documentId],
    queryFn: async () => {
      if (!workflowId || !documentId) return null;

      try {
        const response = await DefaultService.getDocumentCitations(documentId);

        if (!response.data) {
          console.warn("Citations API returned no data");
          return { citations: [], pageDimensions: {} };
        }

        // Transform snake_case API response to camelCase frontend types
        return transformCitationsResponse(response.data);
      } catch (error) {
        console.error("Failed to fetch citations:", error);
        // Return empty structure on error to prevent UI breakage
        return { citations: [], pageDimensions: {} };
      }
    },
    enabled: !!workflowId && !!documentId,
    staleTime: 1000 * 60 * 5,
    gcTime: 1000 * 60 * 10,
  });
};

/**
 * Finds a specific citation by sourceType and sourceId
 */
export function findCitation(
  citations: Citation[],
  sourceType: string,
  sourceId: string
): Citation | undefined {
  return citations.find(
    (citation) =>
      citation.sourceType === sourceType && citation.sourceId === sourceId
  );
}
