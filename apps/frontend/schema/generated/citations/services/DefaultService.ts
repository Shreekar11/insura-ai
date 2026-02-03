/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApiResponse } from '../models/ApiResponse';
import type { Citation } from '../models/Citation';
import type { CitationsResponse } from '../models/CitationsResponse';
import type { PageDimensions } from '../models/PageDimensions';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class DefaultService {
    /**
     * Get all citations for a document
     * @param documentId Unique identifier of the document
     * @returns any Citations retrieved successfully
     * @throws ApiError
     */
    public static getDocumentCitations(
        documentId: string,
    ): CancelablePromise<(ApiResponse & {
        data?: CitationsResponse;
    })> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/documents/{document_id}/citations',
            path: {
                'document_id': documentId,
            },
            errors: {
                401: `Unauthorized`,
                404: `Document not found`,
                500: `Internal server error`,
            },
        });
    }
    /**
     * Get a specific citation by source type and ID
     * @param documentId Unique identifier of the document
     * @param sourceType Type of source being cited
     * @param sourceId Canonical or stable ID of the source item
     * @returns any Citation retrieved successfully
     * @throws ApiError
     */
    public static getCitationBySource(
        documentId: string,
        sourceType: 'effective_coverage' | 'effective_exclusion' | 'endorsement' | 'condition' | 'clause',
        sourceId: string,
    ): CancelablePromise<(ApiResponse & {
        data?: Citation;
    })> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/documents/{document_id}/citations/{source_type}/{source_id}',
            path: {
                'document_id': documentId,
                'source_type': sourceType,
                'source_id': sourceId,
            },
            errors: {
                401: `Unauthorized`,
                404: `Citation not found`,
                500: `Internal server error`,
            },
        });
    }
    /**
     * Get page dimensions for coordinate transformation
     * @param documentId Unique identifier of the document
     * @param pageNumber Page number (1-indexed)
     * @returns any Page dimensions retrieved successfully
     * @throws ApiError
     */
    public static getPageDimensions(
        documentId: string,
        pageNumber: number,
    ): CancelablePromise<(ApiResponse & {
        data?: PageDimensions;
    })> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/documents/{document_id}/pages/{page_number}/dimensions',
            path: {
                'document_id': documentId,
                'page_number': pageNumber,
            },
            errors: {
                401: `Unauthorized`,
                404: `Document or page not found`,
                500: `Internal server error`,
            },
        });
    }
}
