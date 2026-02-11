import { useMutation } from "@tanstack/react-query";
import { DefaultService } from "@/schema/generated/query";
import type { GraphRAGRequest, GraphRAGResponse } from "@/schema/generated/query";

export const useChat = (workflowId: string) => {
  return useMutation({
    mutationFn: async (request: GraphRAGRequest) => {
      const response = await DefaultService.executeQuery(workflowId, request);
      return response as GraphRAGResponse;
    },
  });
};
