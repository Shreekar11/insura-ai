/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $WorkflowExecutionRequest = {
    properties: {
        workflow_name: {
            type: 'string',
            isRequired: true,
        },
        workflow_definition_id: {
            type: 'string',
            isRequired: true,
            format: 'uuid',
        },
        document_ids: {
            type: 'array',
            contains: {
                type: 'string',
                format: 'uuid',
            },
        },
        metadata: {
            type: 'dictionary',
            contains: {
                properties: {
                },
            },
        },
    },
} as const;
