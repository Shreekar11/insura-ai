/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $ResponseMetadata = {
    properties: {
        intent: {
            type: 'string',
            isRequired: true,
        },
        traversal_depth: {
            type: 'number',
            isRequired: true,
        },
        vector_results_count: {
            type: 'number',
            isRequired: true,
        },
        graph_results_count: {
            type: 'number',
            isRequired: true,
        },
        merged_results_count: {
            type: 'number',
            isRequired: true,
        },
        full_text_count: {
            type: 'number',
            isRequired: true,
        },
        summary_count: {
            type: 'number',
            isRequired: true,
        },
        total_context_tokens: {
            type: 'number',
            isRequired: true,
        },
        latency_ms: {
            type: 'number',
            isRequired: true,
        },
        stage_latencies: {
            type: 'dictionary',
            contains: {
                type: 'number',
            },
        },
        graph_available: {
            type: 'boolean',
        },
        fallback_mode: {
            type: 'boolean',
        },
    },
} as const;
