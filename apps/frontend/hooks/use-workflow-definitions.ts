import { useQuery } from "@tanstack/react-query";
import {
  DefaultService,
  WorkflowDefinitionResponse,
} from "@/schema/generated/workflows";

/**
 * Custom hook to fetch workflow definitions using TanStack Query
 *
 * @returns {Object} An object containing the workflow definitions, loading state, error state, and refetch function
 */
export const useWorkflowDefinitions = () => {
  return useQuery({
    queryKey: ["workflow-definitions"],
    queryFn: async () => {
      const response = await DefaultService.getWorkflowDefinitions();
      if (!response?.status) {
        throw new Error("Failed to fetch workflow definitions");
      }
      return (response.data?.definitions || []) as WorkflowDefinitionResponse[];
    },
    staleTime: 1000 * 60 * 5,
    gcTime: 1000 * 60 * 10,
    retry: 2,
    refetchOnWindowFocus: true,
  });
};

export const useWorkflowDefinitionById = (workflowDefinitionId: string) => {
  return useQuery({
    queryKey: ["workflow-definition", workflowDefinitionId],
    queryFn: async () => {
      const response = await DefaultService.getWorkflowDefinitionById(workflowDefinitionId);
      if (!response?.status) {
        throw new Error("Failed to fetch workflow definition");
      }
      return response.data?.definition as WorkflowDefinitionResponse;
    },
    staleTime: 1000 * 60 * 5,
    gcTime: 1000 * 60 * 10,
    retry: 2,
    refetchOnWindowFocus: true,
    enabled: !!workflowDefinitionId,
  });
};
