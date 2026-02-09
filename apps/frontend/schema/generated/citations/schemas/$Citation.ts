/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $Citation = {
    description: `Represents a citation with its location, content, and metadata. Links extracted insurance policy content to its original location in the source PDF.`,
    properties: {
        id: {
            type: 'string',
            description: `Unique identifier for this citation`,
            isRequired: true,
            format: 'uuid',
        },
        document_id: {
            type: 'string',
            description: `ID of the source document`,
            isRequired: true,
            format: 'uuid',
        },
        source_type: {
            type: 'Enum',
            isRequired: true,
        },
        source_id: {
            type: 'string',
            description: `Canonical or stable ID of the source item`,
            isRequired: true,
        },
        spans: {
            type: 'array',
            contains: {
                type: 'CitationSpan',
            },
            isRequired: true,
        },
        verbatim_text: {
            type: 'string',
            description: `The complete verbatim text from the source document`,
            isRequired: true,
        },
        primary_page: {
            type: 'number',
            description: `Primary page number where the citation appears`,
            isRequired: true,
            minimum: 1,
        },
        page_range: {
            type: 'all-of',
            description: `Optional range of pages if citation spans multiple pages`,
            contains: [{
                type: 'PageRange',
            }],
            isNullable: true,
        },
        extraction_confidence: {
            type: 'number',
            description: `Optional confidence score for the extraction (0-1)`,
            isNullable: true,
            format: 'float',
            maximum: 1,
        },
        extraction_method: {
            type: 'Enum',
            isNullable: true,
        },
        clause_reference: {
            type: 'string',
            description: `Optional reference to a specific clause (e.g., '2.3.1')`,
            isNullable: true,
        },
        resolution_method: {
            type: 'Enum',
            isNullable: true,
        },
    },
} as const;
