/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $WorkflowListItem = {
    properties: {
        id: {
            type: 'string',
            format: 'uuid',
        },
        temporal_workflow_id: {
            type: 'string',
            isNullable: true,
        },
        workflow_name: {
            type: 'string',
        },
        workflow_type: {
            type: 'string',
        },
        status: {
            type: 'string',
        },
        metrics: {
            type: 'WorkflowMetrics',
        },
        created_at: {
            type: 'string',
            format: 'date-time',
        },
        updated_at: {
            type: 'string',
            format: 'date-time',
        },
        documents: {
            type: 'array',
            contains: {
                type: 'DocumentSummary',
            },
        },
        stages: {
            type: 'array',
            contains: {
                type: 'StageMetrics',
            },
        },
        recent_events: {
            type: 'array',
            contains: {
                type: 'EventLogItem',
            },
        },
    },
} as const;
