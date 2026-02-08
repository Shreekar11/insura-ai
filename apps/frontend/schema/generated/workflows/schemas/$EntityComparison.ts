/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $EntityComparison = {
    properties: {
        entity_type: {
            type: 'Enum',
        },
        comparison_source: {
            type: 'Enum',
        },
        section_type: {
            type: 'string',
            isNullable: true,
        },
        entity_id: {
            type: 'string',
            isNullable: true,
        },
        entity_name: {
            type: 'string',
        },
        match_type: {
            type: 'Enum',
        },
        confidence: {
            type: 'number',
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
        doc1_summary: {
            type: 'string',
            isNullable: true,
        },
        doc2_summary: {
            type: 'string',
            isNullable: true,
        },
        comparison_summary: {
            type: 'string',
            isNullable: true,
        },
        doc1_content: {
            type: 'dictionary',
            contains: {
                properties: {
                },
            },
            isNullable: true,
        },
        doc2_content: {
            type: 'dictionary',
            contains: {
                properties: {
                },
            },
            isNullable: true,
        },
        doc1_page_range: {
            type: 'dictionary',
            contains: {
                properties: {
                },
            },
            isNullable: true,
        },
        doc2_page_range: {
            type: 'dictionary',
            contains: {
                properties: {
                },
            },
            isNullable: true,
        },
        doc1_confidence: {
            type: 'number',
            isNullable: true,
        },
        doc2_confidence: {
            type: 'number',
            isNullable: true,
        },
        doc1_extraction_id: {
            type: 'string',
            isNullable: true,
            format: 'uuid',
        },
        doc2_extraction_id: {
            type: 'string',
            isNullable: true,
            format: 'uuid',
        },
        severity: {
            type: 'Enum',
        },
    },
} as const;
