'use client'

import { useParams } from "next/navigation";
import { useWorkflowDefinitionById } from "@/hooks/use-workflow-definitions";

export default function WorkflowExecutionPage() {
    const params = useParams();
    const workflowDefinitionId = params.id;
    const { data: workflowDefinition } = useWorkflowDefinitionById(workflowDefinitionId as string);
    console.log(workflowDefinition);
}