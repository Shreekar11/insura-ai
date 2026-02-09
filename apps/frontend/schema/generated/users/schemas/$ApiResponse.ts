/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $ApiResponse = {
    properties: {
        status: {
            type: 'boolean',
            isRequired: true,
        },
        message: {
            type: 'string',
            isRequired: true,
        },
        data: {
            type: 'dictionary',
            contains: {
                properties: {
                },
            },
            isRequired: true,
        },
        meta: {
            type: 'ResponseMeta',
            isRequired: true,
        },
    },
} as const;
