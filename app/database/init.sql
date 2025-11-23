-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    clerk_user_id VARCHAR NOT NULL UNIQUE,
    email VARCHAR NOT NULL,
    full_name VARCHAR,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Documents table
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id),
    file_path VARCHAR NOT NULL,
    mime_type VARCHAR,
    page_count INTEGER,
    status VARCHAR NOT NULL DEFAULT 'uploaded',
    uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Document Pages table
CREATE TABLE IF NOT EXISTS document_pages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    image_path VARCHAR,
    width INTEGER,
    height INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Document Raw Text table
CREATE TABLE IF NOT EXISTS document_raw_text (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_page_id UUID NOT NULL REFERENCES document_pages(id) ON DELETE CASCADE,
    text_content TEXT NOT NULL,
    confidence NUMERIC,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- OCR Results table
CREATE TABLE IF NOT EXISTS ocr_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ocr_provider VARCHAR NOT NULL,
    raw_text TEXT,
    confidence NUMERIC,
    model_version VARCHAR,
    pipeline_run_id UUID,
    source_stage VARCHAR,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- OCR Tokens table
CREATE TABLE IF NOT EXISTS ocr_tokens (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_page_id UUID NOT NULL REFERENCES document_pages(id) ON DELETE CASCADE,
    token VARCHAR NOT NULL,
    x_min INTEGER,
    y_min INTEGER,
    x_max INTEGER,
    y_max INTEGER,
    confidence NUMERIC,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Document Classifications table
CREATE TABLE IF NOT EXISTS document_classifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    classified_type VARCHAR NOT NULL,
    confidence NUMERIC,
    classifier_model VARCHAR,
    decision_details JSON,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Extracted Fields table
CREATE TABLE IF NOT EXISTS extracted_fields (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES documents(id),
    field_name VARCHAR NOT NULL,
    field_value TEXT,
    confidence NUMERIC,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Workflows table
CREATE TABLE IF NOT EXISTS workflows (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES documents(id),
    workflow_type VARCHAR NOT NULL,
    temporal_workflow_id VARCHAR UNIQUE,
    status VARCHAR NOT NULL DEFAULT 'running',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Workflow Run Events table
CREATE TABLE IF NOT EXISTS workflow_run_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    event_type VARCHAR NOT NULL,
    event_payload JSON,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Submissions table
CREATE TABLE IF NOT EXISTS submissions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES documents(id),
    submission_type VARCHAR,
    agent_name VARCHAR,
    insured_name VARCHAR,
    effective_date DATE,
    expiration_date DATE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Policy Comparisons table
CREATE TABLE IF NOT EXISTS policy_comparisons (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES documents(id),
    comparison_json JSON,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Claims table
CREATE TABLE IF NOT EXISTS claims (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES documents(id),
    claim_number VARCHAR,
    insured_name VARCHAR,
    loss_date DATE,
    loss_description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Quotes table
CREATE TABLE IF NOT EXISTS quotes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES documents(id),
    carrier_name VARCHAR,
    premium NUMERIC,
    details JSON,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Proposals table
CREATE TABLE IF NOT EXISTS proposals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES documents(id),
    proposal_json JSON,
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Financial Analysis table
CREATE TABLE IF NOT EXISTS financial_analysis (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES documents(id),
    extracted_metrics JSON,
    risk_assessment TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Property SOV table
CREATE TABLE IF NOT EXISTS property_sov (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES documents(id),
    sov_json JSON,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Document Chunks table
CREATE TABLE IF NOT EXISTS document_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    section_name VARCHAR,
    chunk_index INTEGER NOT NULL DEFAULT 0,
    raw_text TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    section_type VARCHAR,
    subsection_type VARCHAR,
    stable_chunk_id VARCHAR UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Normalized Chunks table
CREATE TABLE IF NOT EXISTS normalized_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    chunk_id UUID NOT NULL REFERENCES document_chunks(id) ON DELETE CASCADE,
    normalized_text TEXT NOT NULL,
    normalization_method VARCHAR NOT NULL DEFAULT 'llm',
    processing_time_ms INTEGER,
    extracted_fields JSONB,
    entities JSONB,
    relationships JSONB,
    model_version VARCHAR,
    quality_score NUMERIC,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Chunk Classification Signals table
CREATE TABLE IF NOT EXISTS chunk_classification_signals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    chunk_id UUID NOT NULL REFERENCES document_chunks(id) ON DELETE CASCADE,
    signals JSON NOT NULL,
    keywords JSON,
    entities JSON,
    model_name VARCHAR NOT NULL,
    model_confidence NUMERIC(5, 4),
    model_version VARCHAR,
    pipeline_run_id UUID,
    source_stage VARCHAR,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Chunk Embeddings table
CREATE TABLE IF NOT EXISTS chunk_embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    chunk_id UUID NOT NULL REFERENCES normalized_chunks(id) ON DELETE CASCADE,
    embedding_model VARCHAR NOT NULL,
    embedding_version VARCHAR NOT NULL,
    embedding_dimension INTEGER NOT NULL,
    embedding JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Canonical Entities table
CREATE TABLE IF NOT EXISTS canonical_entities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_type VARCHAR NOT NULL,
    canonical_key VARCHAR NOT NULL,
    attributes JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(entity_type, canonical_key)
);

-- Chunk Entity Mentions table
CREATE TABLE IF NOT EXISTS chunk_entity_mentions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    chunk_id UUID NOT NULL REFERENCES normalized_chunks(id) ON DELETE CASCADE,
    entity_type VARCHAR NOT NULL,
    raw_value TEXT NOT NULL,
    normalized_value TEXT,
    confidence NUMERIC,
    span_start INTEGER,
    span_end INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Entity Relationships table
CREATE TABLE IF NOT EXISTS entity_relationships (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_entity_id UUID REFERENCES canonical_entities(id),
    target_entity_id UUID REFERENCES canonical_entities(id),
    relationship_type VARCHAR NOT NULL,
    attributes JSONB,
    confidence NUMERIC,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Chunk Entity Links table
CREATE TABLE IF NOT EXISTS chunk_entity_links (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    chunk_id UUID NOT NULL REFERENCES normalized_chunks(id) ON DELETE CASCADE,
    canonical_entity_id UUID NOT NULL REFERENCES canonical_entities(id) ON DELETE CASCADE,
    confidence NUMERIC,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Document Entity Links table
CREATE TABLE IF NOT EXISTS document_entity_links (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    canonical_entity_id UUID NOT NULL REFERENCES canonical_entities(id) ON DELETE CASCADE,
    confidence NUMERIC,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Graph Sync State table
CREATE TABLE IF NOT EXISTS graph_sync_state (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_table VARCHAR NOT NULL,
    source_id UUID NOT NULL,
    neo4j_node_id VARCHAR,
    last_sync_at TIMESTAMP WITH TIME ZONE,
    sync_status VARCHAR DEFAULT 'pending',
    sync_error TEXT
);

-- Embedding Sync State table
CREATE TABLE IF NOT EXISTS embedding_sync_state (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    chunk_id UUID NOT NULL REFERENCES normalized_chunks(id) ON DELETE CASCADE,
    last_embedding_at TIMESTAMP WITH TIME ZONE,
    embedding_model VARCHAR,
    embedding_version VARCHAR,
    sync_status VARCHAR DEFAULT 'pending',
    sync_error TEXT
);

-- SOV Items table
CREATE TABLE IF NOT EXISTS sov_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES documents(id),
    location_number VARCHAR,
    building_number VARCHAR,
    description TEXT,
    construction_type VARCHAR,
    occupancy VARCHAR,
    year_built INTEGER,
    square_footage INTEGER,
    limit NUMERIC,
    deductible NUMERIC,
    additional_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Loss Run Claims table
CREATE TABLE IF NOT EXISTS loss_run_claims (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES documents(id),
    claim_number VARCHAR,
    insured_name VARCHAR,
    loss_date DATE,
    cause_of_loss VARCHAR,
    incurred_amount NUMERIC,
    paid_amount NUMERIC,
    reserve_amount NUMERIC,
    status VARCHAR,
    additional_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chunk_entity_chunk ON chunk_entity_mentions(chunk_id);
CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_chunk ON chunk_embeddings(chunk_id);
CREATE INDEX IF NOT EXISTS idx_document_entity_document ON document_entity_links(document_id);
CREATE INDEX IF NOT EXISTS idx_canonical_entities_key ON canonical_entities(entity_type, canonical_key);
