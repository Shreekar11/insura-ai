/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $GraphRAGResponse = {
    properties: {
        answer: {
            type: 'string',
            isRequired: true,
        },
        metadata: {
            type: 'ResponseMetadata',
            isRequired: true,
        },
        timestamp: {
            type: 'string',
            isRequired: true,
            format: 'date-time',
        },
    },
} as const;
