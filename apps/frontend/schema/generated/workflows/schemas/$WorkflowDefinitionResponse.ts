/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $WorkflowDefinitionResponse = {
    properties: {
        id: {
            type: 'string',
            format: 'uuid',
        },
        name: {
            type: 'string',
        },
        key: {
            type: 'string',
        },
        description: {
            type: 'string',
            isNullable: true,
        },
        input_schema: {
            type: 'dictionary',
            contains: {
                properties: {
                },
            },
            isNullable: true,
        },
        created_at: {
            type: 'string',
            format: 'date-time',
        },
    },
} as const;
