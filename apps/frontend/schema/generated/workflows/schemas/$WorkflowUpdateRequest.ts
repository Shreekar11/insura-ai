/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $WorkflowUpdateRequest = {
    properties: {
        workflow_id: {
            type: 'string',
            isRequired: true,
            format: 'uuid',
        },
        workflow_name: {
            type: 'string',
            isRequired: true,
        },
    },
} as const;
