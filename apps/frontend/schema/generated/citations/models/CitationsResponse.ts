/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Citation } from './Citation';
import type { PageDimensions } from './PageDimensions';
/**
 * Response structure for fetching citations with their associated page dimensions
 */
export type CitationsResponse = {
    /**
     * Array of citations for the document
     */
    citations: Array<Citation>;
    /**
     * Map of page numbers to their dimensions for coordinate transformation
     */
    page_dimensions: Record<string, PageDimensions>;
};

