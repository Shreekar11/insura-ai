/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { DocumentResponse } from './DocumentResponse';
export type MultipleDocumentResponse = {
    total_uploaded: number;
    documents: Array<DocumentResponse>;
    failed_uploads: Array<{
        filename?: string;
        error?: string;
    }>;
};

