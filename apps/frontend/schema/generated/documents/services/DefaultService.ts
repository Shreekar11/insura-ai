/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
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
     * @returns DocumentResponse Document uploaded
     * @throws ApiError
     */
    public static uploadDocument(
        formData?: {
            file?: Blob;
        },
    ): CancelablePromise<DocumentResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/documents/upload',
            formData: formData,
            mediaType: 'multipart/form-data',
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
    ): CancelablePromise<{
        total?: number;
        documents?: Array<DocumentResponse>;
    }> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/documents',
            query: {
                'limit': limit,
                'offset': offset,
            },
        });
    }
    /**
     * Get document details
     * @param documentId
     * @returns DocumentResponse Document details
     * @throws ApiError
     */
    public static getDocument(
        documentId: string,
    ): CancelablePromise<DocumentResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/documents/{document_id}',
            path: {
                'document_id': documentId,
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
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/v1/documents/{document_id}',
            path: {
                'document_id': documentId,
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
    ): CancelablePromise<{
        total?: number;
        entities?: Array<EntityResponse>;
    }> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/documents/{document_id}/entities',
            path: {
                'document_id': documentId,
            },
            query: {
                'entity_type': entityType,
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
    ): CancelablePromise<{
        sections?: Array<SectionResponse>;
    }> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/documents/{document_id}/sections',
            path: {
                'document_id': documentId,
            },
        });
    }
}
