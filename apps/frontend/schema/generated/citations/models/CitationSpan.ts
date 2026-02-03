/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BoundingBox } from './BoundingBox';
/**
 * Represents a continuous span of text on a single page with its location. A citation may span multiple pages.
 */
export type CitationSpan = {
    /**
     * Page number (1-indexed)
     */
    page_number: number;
    /**
     * Array of bounding boxes for this span (multiple if text wraps across lines)
     */
    bounding_boxes: Array<BoundingBox>;
    /**
     * The text content for this span
     */
    text_content: string;
};

