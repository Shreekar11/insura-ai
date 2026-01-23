/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $WorkflowListResponse = {
    properties: {
        total: {
            type: 'number',
        },
        workflows: {
            type: 'array',
            contains: {
                properties: {
                    id: {
                        type: 'string',
                        format: 'uuid',
                    },
                    definition_id: {
                        type: 'string',
                        format: 'uuid',
                    },
                    name: {
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
                },
            },
        },
    },
} as const;
