import { useQuery } from "@tanstack/react-query";
import {
  DefaultService,
  WorkflowDefinitionResponse,
} from "@/schema/generated/workflows";

export const useWorkflowDefinitions = () => {
  try {
    const fetchWorkflowDefinitions = async () => {
      const response = await DefaultService.getWorkflowDefinitions();
      return response;
    };

    const {
      data: response,
      isPending,
      isSuccess,
      isError,
      error,
    } = useQuery({
      queryKey: ["workflow-definitions"],
      queryFn: fetchWorkflowDefinitions,
    });

    if (!response?.status) {
      throw new Error("Failed to fetch workflow definitions");
    }

    const data: WorkflowDefinitionResponse[] = response.data?.definitions || [];

    return {
      data,
      isPending,
      isSuccess,
      isError,
      error,
    };
  } catch (error) {
    console.error("Error fetching workflow definitions:", error);
    return {
      data: [],
      isPending: false,
      isSuccess: false,
      isError: true,
      error,
    };
  }
};
