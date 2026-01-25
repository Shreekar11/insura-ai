/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApiResponse } from '../models/ApiResponse';
import type { DocumentResponse } from '../models/DocumentResponse';
import type { EntityResponse } from '../models/EntityResponse';
import type { SectionResponse } from '../models/SectionResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class DefaultService {
    /**
     * Upload document
     * @param formData
     * @returns any Document uploaded
     * @throws ApiError
     */
    public static uploadDocument(
        formData?: {
            file?: Blob;
        },
    ): CancelablePromise<(ApiResponse & {
        data?: DocumentResponse;
    })> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/documents/upload',
            formData: formData,
            mediaType: 'multipart/form-data',
            errors: {
                400: `Invalid request`,
                401: `Unauthorized`,
                500: `Internal server error`,
            },
        });
    }
    /**
     * List documents
     * @param limit
     * @param offset
     * @returns any List of documents
     * @throws ApiError
     */
    public static listDocuments(
        limit: number = 50,
        offset?: number,
    ): CancelablePromise<(ApiResponse & {
        data?: {
            total?: number;
            documents?: Array<DocumentResponse>;
        };
    })> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/documents',
            query: {
                'limit': limit,
                'offset': offset,
            },
            errors: {
                401: `Unauthorized`,
                500: `Internal server error`,
            },
        });
    }
    /**
     * Get document details
     * @param documentId
     * @returns any Document details
     * @throws ApiError
     */
    public static getDocument(
        documentId: string,
    ): CancelablePromise<(ApiResponse & {
        data?: DocumentResponse;
    })> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/documents/{document_id}',
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
     * Delete document
     * @param documentId
     * @returns any Document deleted
     * @throws ApiError
     */
    public static deleteDocument(
        documentId: string,
    ): CancelablePromise<(ApiResponse & {
        data?: Record<string, any> | null;
    })> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/v1/documents/{document_id}',
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
     * Get document entities
     * @param documentId
     * @param entityType
     * @returns any List of entities
     * @throws ApiError
     */
    public static getDocumentEntities(
        documentId: string,
        entityType?: string,
    ): CancelablePromise<(ApiResponse & {
        data?: {
            total?: number;
            entities?: Array<EntityResponse>;
        };
    })> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/documents/{document_id}/entities',
            path: {
                'document_id': documentId,
            },
            query: {
                'entity_type': entityType,
            },
            errors: {
                401: `Unauthorized`,
                404: `Document not found`,
                500: `Internal server error`,
            },
        });
    }
    /**
     * Get document sections
     * @param documentId
     * @returns any List of sections
     * @throws ApiError
     */
    public static getDocumentSections(
        documentId: string,
    ): CancelablePromise<(ApiResponse & {
        data?: {
            sections?: Array<SectionResponse>;
        };
    })> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/documents/{document_id}/sections',
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
}
