/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $WorkflowStatusResponse = {
    properties: {
        workflow_id: {
            type: 'string',
        },
        status: {
            type: 'string',
        },
        progress: {
            type: 'number',
            isNullable: true,
        },
        current_step: {
            type: 'string',
            isNullable: true,
        },
        error: {
            type: 'string',
            isNullable: true,
        },
    },
} as const;
