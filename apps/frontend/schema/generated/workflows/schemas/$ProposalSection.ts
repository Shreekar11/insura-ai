/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $ProposalSection = {
    properties: {
        section_type: {
            type: 'string',
        },
        title: {
            type: 'string',
        },
        narrative: {
            type: 'string',
        },
        key_findings: {
            type: 'array',
            contains: {
                type: 'dictionary',
                contains: {
                    properties: {
                    },
                },
            },
        },
        raw_data: {
            type: 'dictionary',
            contains: {
                properties: {
                },
            },
            isNullable: true,
        },
        requires_review: {
            type: 'boolean',
        },
        review_reason: {
            type: 'string',
            isNullable: true,
        },
    },
} as const;
