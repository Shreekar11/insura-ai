/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $DocumentResponse = {
    properties: {
        id: {
            type: 'string',
            isRequired: true,
            format: 'uuid',
        },
        status: {
            type: 'string',
            isRequired: true,
        },
        file_path: {
            type: 'string',
            isRequired: true,
        },
        document_name: {
            type: 'string',
            isNullable: true,
        },
        page_count: {
            type: 'number',
            isNullable: true,
        },
        created_at: {
            type: 'string',
            isRequired: true,
            format: 'date-time',
        },
    },
} as const;
