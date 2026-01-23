import { useQuery } from "@tanstack/react-query"
import { DefaultService, WorkflowDefinitionResponse } from "@/schema/generated/workflows"

export const useWorkflowDefinitions = () => {
    const fetchWorkflowDefinitions = async () => {
        const response = await DefaultService.getWorkflowDefinitions()
        return response
    }

    const { data: response, isPending, isSuccess, isError, error } = useQuery({
        queryKey: ["workflow-definitions"],
        queryFn: fetchWorkflowDefinitions,
    });

    // @ts-ignore
    const data: WorkflowDefinitionResponse[] | undefined = response || [];

    return {
        data,
        isPending,
        isSuccess,
        isError,
        error,
    }
}