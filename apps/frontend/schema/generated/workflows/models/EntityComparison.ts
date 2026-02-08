/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type EntityComparison = {
    entity_type?: EntityComparison.entity_type;
    comparison_source?: EntityComparison.comparison_source;
    section_type?: string | null;
    entity_id?: string | null;
    entity_name?: string;
    match_type?: EntityComparison.match_type;
    confidence?: number;
    field_differences?: Array<Record<string, any>> | null;
    reasoning?: string | null;
    doc1_summary?: string | null;
    doc2_summary?: string | null;
    comparison_summary?: string | null;
    doc1_content?: Record<string, any> | null;
    doc2_content?: Record<string, any> | null;
    doc1_page_range?: Record<string, any> | null;
    doc2_page_range?: Record<string, any> | null;
    doc1_confidence?: number | null;
    doc2_confidence?: number | null;
    doc1_extraction_id?: string | null;
    doc2_extraction_id?: string | null;
    severity?: EntityComparison.severity;
};
export namespace EntityComparison {
    export enum entity_type {
        COVERAGE = 'coverage',
        EXCLUSION = 'exclusion',
        SECTION_COVERAGE = 'section_coverage',
        SECTION_EXCLUSION = 'section_exclusion',
    }
    export enum comparison_source {
        EFFECTIVE = 'effective',
        SECTION = 'section',
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

