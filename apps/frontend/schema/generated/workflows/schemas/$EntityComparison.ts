/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $EntityComparison = {
    properties: {
        entity_type: {
            type: 'Enum',
        },
        match_type: {
            type: 'Enum',
        },
        doc1_entity: {
            type: 'dictionary',
            contains: {
                properties: {
                },
            },
            isNullable: true,
        },
        doc1_name: {
            type: 'string',
            isNullable: true,
        },
        doc1_canonical_id: {
            type: 'string',
            isNullable: true,
        },
        doc2_entity: {
            type: 'dictionary',
            contains: {
                properties: {
                },
            },
            isNullable: true,
        },
        doc2_name: {
            type: 'string',
            isNullable: true,
        },
        doc2_canonical_id: {
            type: 'string',
            isNullable: true,
        },
        confidence: {
            type: 'number',
        },
        match_method: {
            type: 'string',
        },
        field_differences: {
            type: 'array',
            contains: {
                type: 'dictionary',
                contains: {
                    properties: {
                    },
                },
            },
            isNullable: true,
        },
        reasoning: {
            type: 'string',
            isNullable: true,
        },
        severity: {
            type: 'Enum',
        },
    },
} as const;
