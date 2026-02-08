/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $ProposalResponse = {
    properties: {
        proposal_id: {
            type: 'string',
            format: 'uuid',
        },
        workflow_id: {
            type: 'string',
            format: 'uuid',
        },
        document_ids: {
            type: 'array',
            contains: {
                type: 'string',
                format: 'uuid',
            },
        },
        insured_name: {
            type: 'string',
        },
        carrier_name: {
            type: 'string',
        },
        policy_type: {
            type: 'string',
        },
        executive_summary: {
            type: 'string',
        },
        sections: {
            type: 'array',
            contains: {
                type: 'ProposalSection',
            },
        },
        comparison_table: {
            type: 'array',
            contains: {
                type: 'ProposalComparisonRow',
            },
        },
        requires_hitl_review: {
            type: 'boolean',
        },
        hitl_items: {
            type: 'array',
            contains: {
                type: 'string',
            },
        },
        quality_score: {
            type: 'number',
            isNullable: true,
        },
        pdf_path: {
            type: 'string',
            isNullable: true,
        },
        metadata: {
            type: 'dictionary',
            contains: {
                properties: {
                },
            },
        },
        created_at: {
            type: 'string',
            format: 'date-time',
        },
    },
} as const;
