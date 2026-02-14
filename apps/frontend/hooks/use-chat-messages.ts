import { useQuery } from "@tanstack/react-query";
import { DefaultService, type WorkflowMessage } from "@/schema/generated/query";

export const useChatMessages = (workflowId: string) => {
  return useQuery({
    queryKey: ["workflow-messages", workflowId],
    queryFn: async () => {
      const response = await DefaultService.getWorkflowMessages(workflowId);
      return response;
    },
    enabled: !!workflowId,
    refetchOnWindowFocus: false,
    staleTime: 1000 * 60 * 5, // 5 minutes
  });
};
