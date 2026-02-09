/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $PageDimensions = {
    description: `Represents the physical dimensions of a PDF page. Dimensions are in points (1/72 inch) following PDF standards.`,
    properties: {
        page_number: {
            type: 'number',
            description: `Page number (1-indexed)`,
            isRequired: true,
            minimum: 1,
        },
        width_points: {
            type: 'number',
            description: `Width of the page in points`,
            isRequired: true,
            format: 'float',
        },
        height_points: {
            type: 'number',
            description: `Height of the page in points`,
            isRequired: true,
            format: 'float',
        },
        rotation: {
            type: 'Enum',
            isRequired: true,
        },
    },
} as const;
