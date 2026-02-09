/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $WorkflowCreateRequest = {
    properties: {
        workflow_definition_id: {
            type: 'string',
            isRequired: true,
            format: 'uuid',
        },
        workflow_name: {
            type: 'string',
        },
    },
} as const;
