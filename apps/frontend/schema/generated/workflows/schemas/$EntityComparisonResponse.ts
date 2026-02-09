/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $EntityComparisonResponse = {
    properties: {
        workflow_id: {
            type: 'string',
            format: 'uuid',
        },
        doc1_id: {
            type: 'string',
            format: 'uuid',
        },
        doc2_id: {
            type: 'string',
            format: 'uuid',
        },
        doc1_name: {
            type: 'string',
        },
        doc2_name: {
            type: 'string',
        },
        summary: {
            type: 'EntityComparisonSummary',
        },
        comparisons: {
            type: 'array',
            contains: {
                type: 'EntityComparison',
            },
        },
        overall_confidence: {
            type: 'number',
        },
        overall_explanation: {
            type: 'string',
            isNullable: true,
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
