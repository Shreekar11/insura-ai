import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  DefaultService,
  EntityComparisonResponse,
} from "@/schema/generated/workflows";

/**
 * Hook for fetching entity comparison data for a workflow.
 * Data is fetched when workflowId is provided.
 */
export const useComparisonData = (workflowId: string | null) => {
  return useQuery({
    queryKey: ["entity-comparison", workflowId],
    queryFn: async () => {
      if (!workflowId) return null;
      const response = await DefaultService.getEntityComparison(workflowId);
      if (!response?.status) {
        throw new Error("Failed to fetch comparison data");
      }
      return response.data as EntityComparisonResponse;
    },
    enabled: !!workflowId,
    staleTime: 1000 * 60 * 5, // 5 minutes
    gcTime: 1000 * 60 * 10, // 10 minutes
  });
};

/**
 * Hook for executing entity comparison for a workflow.
 * Returns a mutation function that can be called to trigger comparison.
 */
export const useExecuteComparison = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (workflowId: string) => {
      const response = await DefaultService.executeEntityComparison(workflowId);
      if (!response?.status) {
        throw new Error("Failed to execute comparison");
      }
      return response.data as EntityComparisonResponse;
    },
    onSuccess: (data, workflowId) => {
      // Invalidate and refetch comparison data
      queryClient.invalidateQueries({
        queryKey: ["entity-comparison", workflowId],
      });
    },
  });
};

// Re-export types for convenience
export type { EntityComparisonResponse };
export type {
  EntityComparison,
  EntityComparisonSummary,
} from "@/schema/generated/workflows";
