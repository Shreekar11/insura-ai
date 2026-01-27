/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $Workflow = {
    properties: {
        id: {
            type: 'string',
            format: 'uuid',
        },
        definition_id: {
            type: 'string',
            format: 'uuid',
        },
        workflow_name: {
            type: 'string',
        },
        definition_name: {
            type: 'string',
        },
        key: {
            type: 'string',
        },
        status: {
            type: 'string',
        },
        created_at: {
            type: 'string',
            format: 'date-time',
        },
        updated_at: {
            type: 'string',
            format: 'date-time',
        },
        duration_seconds: {
            type: 'number',
            isNullable: true,
        },
    },
} as const;
