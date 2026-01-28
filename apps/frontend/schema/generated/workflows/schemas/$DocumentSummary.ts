/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $DocumentSummary = {
    properties: {
        document_id: {
            type: 'string',
            format: 'uuid',
        },
        document_name: {
            type: 'string',
            isNullable: true,
        },
        file_name: {
            type: 'string',
        },
        page_count: {
            type: 'number',
            isNullable: true,
        },
        status: {
            type: 'string',
        },
        uploaded_at: {
            type: 'string',
            format: 'date-time',
        },
    },
} as const;
