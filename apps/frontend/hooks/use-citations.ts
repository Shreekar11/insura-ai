import { useQuery } from "@tanstack/react-query";
import { Citation, CitationsResponse } from "@/types/citation";

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

      // TODO: Replace with actual API call when citations endpoint is implemented
      // Example: const response = await DefaultService.getCitations(workflowId, documentId);

      // For now, return empty citations structure
      return {
        citations: [],
        pageDimensions: {},
      };
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
