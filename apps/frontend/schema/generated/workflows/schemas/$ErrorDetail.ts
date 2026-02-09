/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $ErrorDetail = {
    properties: {
        title: {
            type: 'string',
            isRequired: true,
        },
        status: {
            type: 'number',
            isRequired: true,
        },
        detail: {
            type: 'string',
            isRequired: true,
        },
        instance: {
            type: 'string',
            isNullable: true,
        },
        request_id: {
            type: 'string',
            isRequired: true,
        },
        timestamp: {
            type: 'string',
            isRequired: true,
            format: 'date-time',
        },
    },
} as const;
