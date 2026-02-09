/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Represents a bounding box in PDF coordinate space. Coordinates use the PDF standard coordinate system where origin (0,0) is at the bottom-left corner of the page. All values are in points (1/72 inch).
 */
export type BoundingBox = {
    /**
     * X coordinate of bottom-left corner
     */
    x0: number;
    /**
     * Y coordinate of bottom-left corner
     */
    y0: number;
    /**
     * X coordinate of top-right corner
     */
    x1: number;
    /**
     * Y coordinate of top-right corner
     */
    y1: number;
};

