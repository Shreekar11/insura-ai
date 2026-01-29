import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  DefaultService,
  WorkflowListItem,
  WorkflowCreateRequest,
  WorkflowResponse,
  WorkflowExecutionRequest,
  WorkflowUpdateRequest,
} from "@/schema/generated/workflows";

/**
 * Custom hook to fetch workflows using TanStack Query
 *
 * @param {number} limit - The number of workflows to fetch
 * @param {number} offset - The offset for pagination
 * @returns {Object} An object containing the workflows, total count, loading state, error state, and refetch function
 */
export const useWorkflows = (limit: number = 10, offset: number = 0) => {
  return useQuery({
    queryKey: ["workflows", limit, offset],
    queryFn: async () => {
      const response = await DefaultService.listWorkflows(limit, offset);

      if (!response?.status) {
        throw new Error("Failed to fetch workflows");
      }

      return {
        workflows: (response.data?.workflows || []) as WorkflowListItem[],
        total: response.data?.total || 0,
      };
    },
    staleTime: 1000 * 60 * 5, // Consider data fresh for 5 minutes
    gcTime: 1000 * 60 * 10, // Keep unused data in cache for 10 minutes
    retry: 2, // Retry failed requests twice
    refetchOnWindowFocus: true, // Refetch when window regains focus
  });
};

export const useWorkflowsByDefinitionId = (
  workflowDefinitionId: string,
  limit: number = 10,
  offset: number = 0,
) => {
  return useQuery({
    queryKey: ["workflows", workflowDefinitionId, limit, offset],
    queryFn: async () => {
      const response = await DefaultService.getAllWorkflows(
        workflowDefinitionId,
        limit,
        offset
      );
      if (!response?.status) {
        throw new Error("Failed to fetch workflows");
      }
      return {
        workflows: (response.data?.workflows || []) as WorkflowListItem[],
        total: response.data?.total || 0,
      };
    },
    staleTime: 1000 * 60 * 5,
    gcTime: 1000 * 60 * 10,
    retry: 2,
    refetchOnWindowFocus: true,
  });
};

export const useCreateWorkflow = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: WorkflowCreateRequest) =>
      DefaultService.createWorkflow(request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
    },
  });
};

export const useExecuteWorkflow = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: WorkflowExecutionRequest) =>
      DefaultService.executeWorkflow(request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
    },
  });
};

export const useWorkflowById = (workflowId: string) => {
  return useQuery({
    queryKey: ["workflow", workflowId],
    queryFn: async () => {
      const response = await DefaultService.getWorkflow(workflowId);
      if (!response?.status) {
        throw new Error("Failed to fetch workflow details");
      }
      return response.data as WorkflowResponse;
    },
    enabled: !!workflowId,
    staleTime: 1000 * 60 * 5,
    gcTime: 1000 * 60 * 10,
    retry: 2,
    refetchOnWindowFocus: true,
  });
};

export const useUpdateWorkflow = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: WorkflowUpdateRequest) =>
      DefaultService.updateWorkflow(request),
    onSuccess: (response, variables) => {
      if (response && response.data) {
        queryClient.setQueryData(
          ["workflow", variables.workflow_id],
          response.data
        );
      }
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
      queryClient.invalidateQueries({
        queryKey: ["workflow", variables.workflow_id],
      });
    },
  });
};
