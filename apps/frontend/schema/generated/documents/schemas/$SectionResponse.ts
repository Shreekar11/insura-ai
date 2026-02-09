/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $SectionResponse = {
    properties: {
        section_type: {
            type: 'string',
        },
        chunk_count: {
            type: 'number',
        },
        page_range: {
            type: 'array',
            contains: {
                type: 'number',
            },
        },
    },
} as const;
