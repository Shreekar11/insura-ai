/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $EntityComparisonSummary = {
    properties: {
        total_comparisons: {
            type: 'number',
            description: `Total effective entities compared`,
        },
        coverage_matches: {
            type: 'number',
            description: `Number of exact coverage matches`,
        },
        exclusion_matches: {
            type: 'number',
            description: `Number of exact exclusion matches`,
        },
        total_added: {
            type: 'number',
            description: `Total entities added`,
        },
        total_removed: {
            type: 'number',
            description: `Total entities removed`,
        },
        total_modified: {
            type: 'number',
            description: `Total entities with partial matches`,
        },
        section_coverage_comparisons: {
            type: 'number',
            description: `Number of section-level coverage comparisons`,
        },
        section_exclusion_comparisons: {
            type: 'number',
            description: `Number of section-level exclusion comparisons`,
        },
    },
} as const;
