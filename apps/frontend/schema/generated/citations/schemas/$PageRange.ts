/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $PageRange = {
    description: `Represents a range of pages in a document`,
    properties: {
        start: {
            type: 'number',
            description: `Starting page number (1-indexed, inclusive)`,
            isRequired: true,
            minimum: 1,
        },
        end: {
            type: 'number',
            description: `Ending page number (1-indexed, inclusive)`,
            isRequired: true,
            minimum: 1,
        },
    },
} as const;
