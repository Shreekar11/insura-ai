/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type GraphRAGRequest = {
    /**
     * User's natural language question
     */
    query: string;
    /**
     * Specific documents to query (None = all workflow docs)
     */
    document_ids?: Array<string> | null;
    include_sources?: boolean;
    max_context_tokens?: number;
    intent_override?: GraphRAGRequest.intent_override | null;
};
export namespace GraphRAGRequest {
    export enum intent_override {
        QA = 'QA',
        ANALYSIS = 'ANALYSIS',
        AUDIT = 'AUDIT',
    }
}

