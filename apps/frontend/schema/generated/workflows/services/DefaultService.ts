/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApiResponse } from '../models/ApiResponse';
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
     * @returns any Workflow started
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
    ): CancelablePromise<(ApiResponse & {
        data?: WorkflowExecutionResponse;
    })> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/workflows/execute',
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
     * List workflows
     * @param limit
     * @param offset
     * @returns any List of workflows
     * @throws ApiError
     */
    public static listWorkflows(
        limit: number = 50,
        offset?: number,
    ): CancelablePromise<(ApiResponse & {
        data?: WorkflowListResponse;
    })> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/workflows',
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
     * Get workflow details
     * @param workflowId
     * @returns any Workflow details
     * @throws ApiError
     */
    public static getWorkflow(
        workflowId: string,
    ): CancelablePromise<(ApiResponse & {
        data?: WorkflowResponse;
    })> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/workflows/{workflow_id}',
            path: {
                'workflow_id': workflowId,
            },
            errors: {
                401: `Unauthorized`,
                404: `Workflow not found`,
                500: `Internal server error`,
            },
        });
    }
    /**
     * Get all workflows for a workflow definition
     * @param workflowDefinitionId
     * @returns any List of workflows
     * @throws ApiError
     */
    public static getAllWorkflows(
        workflowDefinitionId: string,
    ): CancelablePromise<(ApiResponse & {
        data?: WorkflowListResponse;
    })> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/workflows/all/{workflow_definition_id}',
            path: {
                'workflow_definition_id': workflowDefinitionId,
            },
            errors: {
                401: `Unauthorized`,
                404: `Workflows not found`,
                500: `Internal server error`,
            },
        });
    }
    /**
     * Get workflow definitions
     * @returns any List of workflow definitions
     * @throws ApiError
     */
    public static getWorkflowDefinitions(): CancelablePromise<(ApiResponse & {
        data?: {
            definitions?: Array<WorkflowDefinitionResponse>;
        };
    })> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/workflows/definitions',
            errors: {
                500: `Internal server error`,
            },
        });
    }
    /**
     * Get workflow definition by id
     * @param workflowDefinitionId
     * @returns any Workflow definition
     * @throws ApiError
     */
    public static getWorkflowDefinitionById(
        workflowDefinitionId: string,
    ): CancelablePromise<(ApiResponse & {
        data?: {
            definition?: WorkflowDefinitionResponse;
        };
    })> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/workflows/definitions/{workflow_definition_id}',
            path: {
                'workflow_definition_id': workflowDefinitionId,
            },
            errors: {
                500: `Internal server error`,
            },
        });
    }
    /**
     * Get workflow status
     * @param workflowId
     * @returns any Workflow status
     * @throws ApiError
     */
    public static getWorkflowStatus(
        workflowId: string,
    ): CancelablePromise<(ApiResponse & {
        data?: WorkflowStatusResponse;
    })> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/workflows/{workflow_id}/status',
            path: {
                'workflow_id': workflowId,
            },
            errors: {
                404: `Workflow not found`,
                500: `Internal server error`,
            },
        });
    }
    /**
     * Get extracted data
     * @param workflowId
     * @param documentId
     * @returns any Extracted data
     * @throws ApiError
     */
    public static getExtractedData(
        workflowId: string,
        documentId: string,
    ): CancelablePromise<(ApiResponse & {
        data?: WorkflowExtractedDataResponse;
    })> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/workflows/{workflow_id}/extracted/{document_id}',
            path: {
                'workflow_id': workflowId,
                'document_id': documentId,
            },
            errors: {
                401: `Unauthorized`,
                404: `Workflow or document not found`,
                500: `Internal server error`,
            },
        });
    }
    /**
     * Start document extraction
     * @param requestBody
     * @returns any Extraction started
     * @throws ApiError
     */
    public static startExtraction(
        requestBody: WorkflowExtractRequest,
    ): CancelablePromise<(ApiResponse & {
        data?: WorkflowExecutionResponse;
    })> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/workflows/extract',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                400: `Invalid request`,
                401: `Unauthorized`,
                500: `Internal server error`,
            },
        });
    }
}
