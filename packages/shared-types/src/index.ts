// API Request/Response types
export interface DocumentUploadRequest {
    file: File;
    documentType: string;
}

export interface PageAnalysisResponse {
    pageNumber: number;
    content: string;
    entities: Entity[];
}

export interface Entity {
    id: string;
    type: string;
    value: string;
    confidence: number;
}
