import { useQuery } from "@tanstack/react-query";
import { DefaultService, ProposalResponse } from "@/schema/generated/workflows";

/**
 * Custom hook to fetch proposal data for a workflow
 * 
 * @param {string} workflowId - The ID of the workflow
 * @returns {Object} An object containing the proposal data, loading state, error state, and refetch function
 */
export const useProposalData = (workflowId: string) => {
  return useQuery({
    queryKey: ["proposal", workflowId],
    queryFn: async () => {
      const response = await DefaultService.getProposal(workflowId);

      if (!response?.status) {
        throw new Error("Failed to fetch proposal data");
      }

      return response.data as ProposalResponse;
    },
    enabled: !!workflowId,
    staleTime: 1000 * 60 * 5,
    gcTime: 1000 * 60 * 10,
    retry: 2,
    refetchOnWindowFocus: true,
  });
};
