/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ResponseMetadata = {
    intent: string;
    traversal_depth: number;
    vector_results_count: number;
    graph_results_count: number;
    merged_results_count: number;
    full_text_count: number;
    summary_count: number;
    total_context_tokens: number;
    latency_ms: number;
    stage_latencies?: Record<string, number>;
    graph_available?: boolean;
    fallback_mode?: boolean;
};

