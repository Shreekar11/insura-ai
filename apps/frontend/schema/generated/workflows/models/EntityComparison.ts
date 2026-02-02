/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type EntityComparison = {
    entity_type?: EntityComparison.entity_type;
    match_type?: EntityComparison.match_type;
    doc1_entity?: Record<string, any> | null;
    doc1_name?: string | null;
    doc1_canonical_id?: string | null;
    doc2_entity?: Record<string, any> | null;
    doc2_name?: string | null;
    doc2_canonical_id?: string | null;
    confidence?: number;
    match_method?: string;
    field_differences?: Array<Record<string, any>> | null;
    reasoning?: string | null;
    severity?: EntityComparison.severity;
};
export namespace EntityComparison {
    export enum entity_type {
        COVERAGE = 'coverage',
        EXCLUSION = 'exclusion',
    }
    export enum match_type {
        MATCH = 'match',
        PARTIAL_MATCH = 'partial_match',
        ADDED = 'added',
        REMOVED = 'removed',
        NO_MATCH = 'no_match',
    }
    export enum severity {
        LOW = 'low',
        MEDIUM = 'medium',
        HIGH = 'high',
    }
}

