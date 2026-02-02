/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { DocumentSummary } from './DocumentSummary';
import type { EventLogItem } from './EventLogItem';
import type { StageMetrics } from './StageMetrics';
import type { WorkflowMetrics } from './WorkflowMetrics';
export type WorkflowResponse = {
    id?: string;
    temporal_workflow_id?: string | null;
    workflow_name?: string;
    definition_id?: string;
    definition_name?: string;
    workflow_type?: string;
    status?: string;
    metrics?: WorkflowMetrics;
    created_at?: string;
    updated_at?: string;
    duration_seconds?: number | null;
    documents?: Array<DocumentSummary>;
    stages?: Array<StageMetrics>;
    recent_events?: Array<EventLogItem>;
};

