/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ProposalComparisonRow } from './ProposalComparisonRow';
import type { ProposalSection } from './ProposalSection';
export type ProposalResponse = {
    proposal_id?: string;
    workflow_id?: string;
    document_ids?: Array<string>;
    insured_name?: string;
    carrier_name?: string;
    policy_type?: string;
    executive_summary?: string;
    sections?: Array<ProposalSection>;
    comparison_table?: Array<ProposalComparisonRow>;
    requires_hitl_review?: boolean;
    hitl_items?: Array<string>;
    quality_score?: number | null;
    pdf_path?: string | null;
    metadata?: Record<string, any>;
    created_at?: string;
};

