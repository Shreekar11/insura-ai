/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $GraphRAGRequest = {
    properties: {
        query: {
            type: 'string',
            description: `User's natural language question`,
            isRequired: true,
            minLength: 1,
        },
        document_ids: {
            type: 'array',
            contains: {
                type: 'string',
                format: 'uuid',
            },
            isNullable: true,
        },
        include_sources: {
            type: 'boolean',
        },
        max_context_tokens: {
            type: 'number',
            maximum: 32000,
            minimum: 1000,
        },
        intent_override: {
            type: 'Enum',
            isNullable: true,
        },
    },
} as const;
