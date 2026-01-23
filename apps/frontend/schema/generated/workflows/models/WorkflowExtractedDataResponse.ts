/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type WorkflowExtractedDataResponse = {
    workflow_id?: string;
    document_id?: string;
    extracted_data?: {
        sections?: Array<{
            section_type?: string;
            fields?: Record<string, any>;
            confidence?: number;
        }>;
        entities?: Array<{
            entity_type?: string;
            fields?: Record<string, any>;
            confidence?: number;
        }>;
    };
};

