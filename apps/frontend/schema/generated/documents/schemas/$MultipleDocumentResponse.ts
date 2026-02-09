/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $MultipleDocumentResponse = {
    properties: {
        total_uploaded: {
            type: 'number',
            isRequired: true,
        },
        documents: {
            type: 'array',
            contains: {
                type: 'DocumentResponse',
            },
            isRequired: true,
        },
        failed_uploads: {
            type: 'array',
            contains: {
                properties: {
                    filename: {
                        type: 'string',
                    },
                    error: {
                        type: 'string',
                    },
                },
            },
            isRequired: true,
        },
    },
} as const;
