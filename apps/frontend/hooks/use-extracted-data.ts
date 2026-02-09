import { useQuery } from "@tanstack/react-query";
import {
  DefaultService,
  WorkflowExtractedDataResponse,
} from "@/schema/generated/workflows";

/**
 * Hook for lazy-fetching extracted data for a document in a workflow.
 * Data is only fetched when both workflowId and documentId are provided.
 */
export const useExtractedData = (
  workflowId: string | null,
  documentId: string | null
) => {
  return useQuery({
    queryKey: ["extracted-data", workflowId, documentId],
    queryFn: async () => {
      if (!workflowId || !documentId) return null;
      const response = await DefaultService.getExtractedData(
        workflowId,
        documentId
      );
      if (!response?.status) {
        throw new Error("Failed to fetch extracted data");
      }
      return response.data as WorkflowExtractedDataResponse;
    },
    enabled: !!workflowId && !!documentId,
    staleTime: 1000 * 60 * 5,
    gcTime: 1000 * 60 * 10,
  });
};
