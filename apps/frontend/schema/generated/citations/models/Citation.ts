/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CitationSpan } from './CitationSpan';
import type { PageRange } from './PageRange';
/**
 * Represents a citation with its location, content, and metadata. Links extracted insurance policy content to its original location in the source PDF.
 */
export type Citation = {
    /**
     * Unique identifier for this citation
     */
    id: string;
    /**
     * ID of the source document
     */
    document_id: string;
    /**
     * Type of the source being cited
     */
    source_type: Citation.source_type;
    /**
     * Canonical or stable ID of the source item
     */
    source_id: string;
    /**
     * Array of spans representing the citation across one or more pages
     */
    spans: Array<CitationSpan>;
    /**
     * The complete verbatim text from the source document
     */
    verbatim_text: string;
    /**
     * Primary page number where the citation appears
     */
    primary_page: number;
    /**
     * Optional range of pages if citation spans multiple pages
     */
    page_range?: PageRange | null;
    /**
     * Optional confidence score for the extraction (0-1)
     */
    extraction_confidence?: number | null;
    /**
     * Optional method used to extract this citation
     */
    extraction_method?: Citation.extraction_method | null;
    /**
     * Optional reference to a specific clause (e.g., '2.3.1')
     */
    clause_reference?: string | null;
    /**
     * How the citation was resolved: direct_text_match (exact/fuzzy word match), semantic_chunk_match (embedding-based chunk search), or placeholder (full-page fallback)
     */
    resolution_method?: Citation.resolution_method | null;
};
export namespace Citation {
    /**
     * Type of the source being cited
     */
    export enum source_type {
        EFFECTIVE_COVERAGE = 'effective_coverage',
        EFFECTIVE_EXCLUSION = 'effective_exclusion',
        ENDORSEMENT = 'endorsement',
        CONDITION = 'condition',
        CLAUSE = 'clause',
    }
    /**
     * Optional method used to extract this citation
     */
    export enum extraction_method {
        DOCLING = 'docling',
        PDFPLUMBER = 'pdfplumber',
        MANUAL = 'manual',
    }
    /**
     * How the citation was resolved: direct_text_match (exact/fuzzy word match), semantic_chunk_match (embedding-based chunk search), or placeholder (full-page fallback)
     */
    export enum resolution_method {
        DIRECT_TEXT_MATCH = 'direct_text_match',
        SEMANTIC_CHUNK_MATCH = 'semantic_chunk_match',
        PLACEHOLDER = 'placeholder',
    }
}

