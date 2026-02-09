/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type EntityComparisonSummary = {
    /**
     * Total effective entities compared
     */
    total_comparisons?: number;
    /**
     * Number of exact coverage matches
     */
    coverage_matches?: number;
    /**
     * Number of exact exclusion matches
     */
    exclusion_matches?: number;
    /**
     * Total entities added
     */
    total_added?: number;
    /**
     * Total entities removed
     */
    total_removed?: number;
    /**
     * Total entities with partial matches
     */
    total_modified?: number;
    /**
     * Number of section-level coverage comparisons
     */
    section_coverage_comparisons?: number;
    /**
     * Number of section-level exclusion comparisons
     */
    section_exclusion_comparisons?: number;
};

