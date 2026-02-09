/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Represents the physical dimensions of a PDF page. Dimensions are in points (1/72 inch) following PDF standards.
 */
export type PageDimensions = {
    /**
     * Page number (1-indexed)
     */
    page_number: number;
    /**
     * Width of the page in points
     */
    width_points: number;
    /**
     * Height of the page in points
     */
    height_points: number;
    /**
     * Rotation of the page in degrees
     */
    rotation: PageDimensions.rotation;
};
export namespace PageDimensions {
    /**
     * Rotation of the page in degrees
     */
    export enum rotation {
        '_0' = 0,
        '_90' = 90,
        '_180' = 180,
        '_270' = 270,
    }
}

