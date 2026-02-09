/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $EntityResponse = {
    properties: {
        id: {
            type: 'string',
            format: 'uuid',
        },
        type: {
            type: 'string',
        },
        value: {
            type: 'string',
        },
        confidence: {
            type: 'number',
            isNullable: true,
        },
        extracted_fields: {
            type: 'dictionary',
            contains: {
                properties: {
                },
            },
        },
    },
} as const;
