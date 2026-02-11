/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GraphRAGRequest } from '../models/GraphRAGRequest';
import type { GraphRAGResponse } from '../models/GraphRAGResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class DefaultService {
    /**
     * Execute GraphRAG query
     * @param workflowId
     * @param requestBody
     * @returns GraphRAGResponse Successful retrieval
     * @throws ApiError
     */
    public static executeQuery(
        workflowId: string,
        requestBody: GraphRAGRequest,
    ): CancelablePromise<GraphRAGResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/query/{workflow_id}',
            path: {
                'workflow_id': workflowId,
            },
            body: requestBody,
            mediaType: 'application/json',
        });
    }
}
