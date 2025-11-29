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
    content_hash VARCHAR(64),
    model_version VARCHAR,
    prompt_version VARCHAR,
    pipeline_run_id VARCHAR,
    source_stage VARCHAR,
    quality_score NUMERIC,
    extracted_at TIMESTAMP WITH TIME ZONE,
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
    CONSTRAINT uq_entity_type_canonical_key UNIQUE(entity_type, canonical_key)
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
    chunk_id UUID REFERENCES document_chunks(id),
    location_number VARCHAR,
    building_number VARCHAR,
    description TEXT,
    address TEXT,
    construction_type VARCHAR,
    occupancy VARCHAR,
    year_built INTEGER,
    square_footage INTEGER,
    building_limit NUMERIC,
    contents_limit NUMERIC,
    bi_limit NUMERIC,
    total_insured_value NUMERIC,
    additional_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Loss Run Claims table
CREATE TABLE IF NOT EXISTS loss_run_claims (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES documents(id),
    chunk_id UUID REFERENCES document_chunks(id),
    claim_number VARCHAR,
    policy_number VARCHAR,
    insured_name VARCHAR,
    loss_date DATE,
    report_date DATE,
    cause_of_loss VARCHAR,
    description TEXT,
    incurred_amount NUMERIC,
    paid_amount NUMERIC,
    reserve_amount NUMERIC,
    status VARCHAR,
    additional_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Policy Items table
CREATE TABLE IF NOT EXISTS policy_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES documents(id),
    chunk_id UUID REFERENCES document_chunks(id),
    policy_number VARCHAR,
    policy_type VARCHAR,
    insured_name VARCHAR,
    effective_date DATE,
    expiration_date DATE,
    premium_amount NUMERIC,
    coverage_limits JSONB,
    deductibles JSONB,
    carrier_name VARCHAR,
    agent_name VARCHAR,
    additional_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Endorsement Items table
CREATE TABLE IF NOT EXISTS endorsement_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES documents(id),
    chunk_id UUID REFERENCES document_chunks(id),
    endorsement_number VARCHAR,
    policy_number VARCHAR,
    effective_date DATE,
    change_type VARCHAR,
    description TEXT,
    premium_change NUMERIC,
    coverage_changes JSONB,
    additional_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Invoice Items table
CREATE TABLE IF NOT EXISTS invoice_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES documents(id),
    chunk_id UUID REFERENCES document_chunks(id),
    invoice_number VARCHAR,
    policy_number VARCHAR,
    invoice_date DATE,
    due_date DATE,
    total_amount NUMERIC,
    amount_paid NUMERIC,
    balance_due NUMERIC,
    payment_status VARCHAR,
    payment_method VARCHAR,
    additional_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Condition Items table
CREATE TABLE IF NOT EXISTS condition_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES documents(id),
    chunk_id UUID REFERENCES document_chunks(id),
    condition_type VARCHAR,
    title VARCHAR,
    description TEXT,
    applies_to VARCHAR,
    requirements JSONB,
    consequences TEXT,
    reference VARCHAR,
    additional_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Coverage Items table
CREATE TABLE IF NOT EXISTS coverage_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES documents(id),
    chunk_id UUID REFERENCES document_chunks(id),
    coverage_name VARCHAR,
    coverage_type VARCHAR,
    limit_amount NUMERIC,
    deductible_amount NUMERIC,
    premium_amount NUMERIC,
    description TEXT,
    sub_limits JSONB,
    exclusions JSONB,
    conditions JSONB,
    per_occurrence BOOLEAN,
    aggregate BOOLEAN,
    additional_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Exclusion Items table
CREATE TABLE IF NOT EXISTS exclusion_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES documents(id),
    chunk_id UUID REFERENCES document_chunks(id),
    exclusion_type VARCHAR,
    title VARCHAR,
    description TEXT,
    applies_to VARCHAR,
    scope VARCHAR,
    exceptions JSONB,
    rationale TEXT,
    reference VARCHAR,
    additional_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- KYC Items table
CREATE TABLE IF NOT EXISTS kyc_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES documents(id),
    chunk_id UUID REFERENCES document_chunks(id),
    customer_name VARCHAR,
    customer_type VARCHAR,
    date_of_birth DATE,
    incorporation_date DATE,
    tax_id VARCHAR,
    business_type VARCHAR,
    industry VARCHAR,
    address TEXT,
    city VARCHAR,
    state VARCHAR,
    zip_code VARCHAR,
    country VARCHAR,
    phone VARCHAR,
    email VARCHAR,
    website VARCHAR,
    identification_type VARCHAR,
    identification_number VARCHAR,
    identification_issuer VARCHAR,
    identification_expiry DATE,
    authorized_signers JSONB,
    ownership_structure TEXT,
    annual_revenue NUMERIC,
    employee_count INTEGER,
    additional_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Claim Items table
CREATE TABLE IF NOT EXISTS claim_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES documents(id),
    chunk_id UUID REFERENCES document_chunks(id),
    claim_number VARCHAR,
    policy_number VARCHAR,
    claimant_name VARCHAR,
    loss_date DATE,
    report_date DATE,
    claim_type VARCHAR,
    loss_description TEXT,
    loss_location TEXT,
    claim_amount NUMERIC,
    paid_amount NUMERIC,
    reserve_amount NUMERIC,
    claim_status VARCHAR,
    adjuster_name VARCHAR,
    denial_reason TEXT,
    additional_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_chunk_entity_chunk ON chunk_entity_mentions(chunk_id);
CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_chunk ON chunk_embeddings(chunk_id);
CREATE INDEX IF NOT EXISTS idx_document_entity_document ON document_entity_links(document_id);
CREATE INDEX IF NOT EXISTS idx_canonical_entities_key ON canonical_entities(entity_type, canonical_key);
CREATE INDEX IF NOT EXISTS idx_normalized_chunks_content_hash ON normalized_chunks(content_hash);
CREATE INDEX IF NOT EXISTS idx_normalized_chunks_pipeline_run ON normalized_chunks(pipeline_run_id);
