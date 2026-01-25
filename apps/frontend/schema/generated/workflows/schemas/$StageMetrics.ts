/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $StageMetrics = {
    properties: {
        stage_name: {
            type: 'string',
        },
        status: {
            type: 'string',
        },
        started_at: {
            type: 'string',
            isNullable: true,
            format: 'date-time',
        },
        completed_at: {
            type: 'string',
            isNullable: true,
            format: 'date-time',
        },
        duration_seconds: {
            type: 'number',
            isNullable: true,
        },
    },
} as const;
