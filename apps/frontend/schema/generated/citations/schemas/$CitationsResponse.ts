/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $CitationsResponse = {
    description: `Response structure for fetching citations with their associated page dimensions`,
    properties: {
        citations: {
            type: 'array',
            contains: {
                type: 'Citation',
            },
            isRequired: true,
        },
        page_dimensions: {
            type: 'dictionary',
            contains: {
                type: 'PageDimensions',
            },
            isRequired: true,
        },
    },
} as const;
