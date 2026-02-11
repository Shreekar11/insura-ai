/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type WorkflowMessage = {
    id: string;
    role: WorkflowMessage.role;
    content: string;
    additional_metadata?: Record<string, any> | null;
    created_at: string;
};
export namespace WorkflowMessage {
    export enum role {
        USER = 'user',
        MODEL = 'model',
    }
}

