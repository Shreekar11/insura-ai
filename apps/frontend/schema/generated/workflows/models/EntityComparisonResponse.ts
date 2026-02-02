/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { EntityComparison } from './EntityComparison';
import type { EntityComparisonSummary } from './EntityComparisonSummary';
export type EntityComparisonResponse = {
    workflow_id?: string;
    doc1_id?: string;
    doc2_id?: string;
    doc1_name?: string;
    doc2_name?: string;
    summary?: EntityComparisonSummary;
    comparisons?: Array<EntityComparison>;
    overall_confidence?: number;
    overall_explanation?: string | null;
    metadata?: Record<string, any>;
};

