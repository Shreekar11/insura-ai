/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { WorkflowDefinitionResponse } from '../models/WorkflowDefinitionResponse';
import type { WorkflowExecutionResponse } from '../models/WorkflowExecutionResponse';
import type { WorkflowExtractedDataResponse } from '../models/WorkflowExtractedDataResponse';
import type { WorkflowExtractRequest } from '../models/WorkflowExtractRequest';
import type { WorkflowListResponse } from '../models/WorkflowListResponse';
import type { WorkflowResponse } from '../models/WorkflowResponse';
import type { WorkflowStatusResponse } from '../models/WorkflowStatusResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class DefaultService {
    /**
     * Execute workflow
     * @param formData
     * @returns WorkflowExecutionResponse Workflow started
     * @throws ApiError
     */
    public static executeWorkflow(
        formData?: {
            workflow_name: string;
            workflow_definition_id: string;
            metadata_json?: string;
            file1: Blob;
            file2?: Blob;
        },
    ): CancelablePromise<WorkflowExecutionResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/workflows/execute',
            formData: formData,
            mediaType: 'multipart/form-data',
        });
    }
    /**
     * List workflows
     * @param limit
     * @param offset
     * @returns WorkflowListResponse List of workflows
     * @throws ApiError
     */
    public static listWorkflows(
        limit: number = 50,
        offset?: number,
    ): CancelablePromise<WorkflowListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/workflows',
            query: {
                'limit': limit,
                'offset': offset,
            },
        });
    }
    /**
     * Get workflow definitions
     * @returns any List of workflow definitions
     * @throws ApiError
     */
    public static getWorkflowDefinitions(): CancelablePromise<{
        definitions?: Array<WorkflowDefinitionResponse>;
    }> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/workflows/definitions',
        });
    }
    /**
     * Get workflow details
     * @param workflowId
     * @returns WorkflowResponse Workflow details
     * @throws ApiError
     */
    public static getWorkflow(
        workflowId: string,
    ): CancelablePromise<WorkflowResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/workflows/{workflow_id}',
            path: {
                'workflow_id': workflowId,
            },
            errors: {
                404: `Workflow not found`,
            },
        });
    }
    /**
     * Get workflow status
     * @param workflowId
     * @returns WorkflowStatusResponse Workflow status
     * @throws ApiError
     */
    public static getWorkflowStatus(
        workflowId: string,
    ): CancelablePromise<WorkflowStatusResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/workflows/{workflow_id}/status',
            path: {
                'workflow_id': workflowId,
            },
        });
    }
    /**
     * Get extracted data
     * @param workflowId
     * @param documentId
     * @returns WorkflowExtractedDataResponse Extracted data
     * @throws ApiError
     */
    public static getExtractedData(
        workflowId: string,
        documentId: string,
    ): CancelablePromise<WorkflowExtractedDataResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/workflows/{workflow_id}/extracted/{document_id}',
            path: {
                'workflow_id': workflowId,
                'document_id': documentId,
            },
            errors: {
                404: `Workflow not found`,
            },
        });
    }
    /**
     * Start document extraction
     * @param requestBody
     * @returns WorkflowExecutionResponse Extraction started
     * @throws ApiError
     */
    public static startExtraction(
        requestBody: WorkflowExtractRequest,
    ): CancelablePromise<WorkflowExecutionResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/workflows/extract',
            body: requestBody,
            mediaType: 'application/json',
        });
    }
}
