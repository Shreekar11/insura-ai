/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $BoundingBox = {
    description: `Represents a bounding box in PDF coordinate space. Coordinates use the PDF standard coordinate system where origin (0,0) is at the bottom-left corner of the page. All values are in points (1/72 inch).`,
    properties: {
        x0: {
            type: 'number',
            description: `X coordinate of bottom-left corner`,
            isRequired: true,
            format: 'float',
        },
        y0: {
            type: 'number',
            description: `Y coordinate of bottom-left corner`,
            isRequired: true,
            format: 'float',
        },
        x1: {
            type: 'number',
            description: `X coordinate of top-right corner`,
            isRequired: true,
            format: 'float',
        },
        y1: {
            type: 'number',
            description: `Y coordinate of top-right corner`,
            isRequired: true,
            format: 'float',
        },
    },
} as const;
