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
    text NOT NULL,
    markdown NOT NULL,
    additional_metadata JSONB NOT NULL,
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

-- ============================================================================
-- CORE WORKFLOW TABLES (Enhanced)
-- ============================================================================

-- Main workflows table (enhanced with tracking fields)
CREATE TABLE IF NOT EXISTS workflows (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    
    -- Temporal identifiers
    temporal_workflow_id VARCHAR UNIQUE NOT NULL,
    temporal_run_id VARCHAR NOT NULL,
    
    -- Workflow metadata
    workflow_type VARCHAR NOT NULL, -- 'process_document', 'reprocess_ocr', etc.
    parent_workflow_id UUID REFERENCES workflows(id), -- For child workflows
    
    -- Status tracking
    status VARCHAR NOT NULL DEFAULT 'running' CHECK (status IN (
        'running', 'completed', 'failed', 'cancelled', 
        'continued_as_new', 'timed_out', 'terminated'
    )),
    
    -- Progress tracking
    current_phase VARCHAR, -- 'ocr', 'normalization', 'entity_resolution', 'graph_construction'
    progress_percentage INTEGER DEFAULT 0 CHECK (progress_percentage BETWEEN 0 AND 100),
    
    -- Timing
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    
    -- Error tracking
    error_message TEXT,
    error_stack_trace TEXT,
    retry_count INTEGER DEFAULT 0,
    
    -- Metadata
    input_params JSONB, -- Workflow input parameters
    result JSONB, -- Final workflow result
    
    -- Audit
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for workflows
CREATE INDEX idx_workflows_document_id ON workflows(document_id);
CREATE INDEX idx_workflows_temporal_workflow_id ON workflows(temporal_workflow_id);
CREATE INDEX idx_workflows_status ON workflows(status);
CREATE INDEX idx_workflows_workflow_type ON workflows(workflow_type);
CREATE INDEX idx_workflows_parent_id ON workflows(parent_workflow_id);
CREATE INDEX idx_workflows_current_phase ON workflows(current_phase);
CREATE INDEX idx_workflows_started_at ON workflows(started_at DESC);

-- ============================================================================
-- CHILD WORKFLOWS TRACKING
-- ============================================================================

-- Track child workflow execution
CREATE TABLE IF NOT EXISTS child_workflows (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    parent_workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    child_workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    
    -- Child workflow details
    child_type VARCHAR NOT NULL, -- 'ocr_extraction', 'normalization', etc.
    execution_order INTEGER NOT NULL, -- 1, 2, 3, 4 for sequential execution
    
    -- Status
    status VARCHAR NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending', 'running', 'completed', 'failed', 'skipped'
    )),
    
    -- Timing
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    duration_seconds INTEGER GENERATED ALWAYS AS (
        EXTRACT(EPOCH FROM (completed_at - started_at))
    ) STORED,
    
    -- Results
    result JSONB,
    error_message TEXT,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE(parent_workflow_id, execution_order)
);

CREATE INDEX idx_child_workflows_parent ON child_workflows(parent_workflow_id);
CREATE INDEX idx_child_workflows_child ON child_workflows(child_workflow_id);
CREATE INDEX idx_child_workflows_status ON child_workflows(status);

-- ============================================================================
-- WORKFLOW EVENTS (Enhanced)
-- ============================================================================

-- Workflow run events with enhanced tracking
CREATE TABLE IF NOT EXISTS workflow_run_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    
    -- Event classification
    event_type VARCHAR NOT NULL, -- 'workflow_started', 'activity_completed', 'signal_received', etc.
    event_category VARCHAR NOT NULL DEFAULT 'info' CHECK (event_category IN (
        'info', 'warning', 'error', 'milestone'
    )),
    
    -- Event details
    event_name VARCHAR, -- Human-readable event name
    event_payload JSONB,
    
    -- Activity tracking (if applicable)
    activity_id VARCHAR, -- Temporal activity ID
    activity_type VARCHAR, -- 'extract_ocr', 'batch_process_chunks', etc.
    
    -- Timing
    event_timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for events
CREATE INDEX idx_workflow_events_workflow_id ON workflow_run_events(workflow_id);
CREATE INDEX idx_workflow_events_type ON workflow_run_events(event_type);
CREATE INDEX idx_workflow_events_category ON workflow_run_events(event_category);
CREATE INDEX idx_workflow_events_timestamp ON workflow_run_events(event_timestamp DESC);
CREATE INDEX idx_workflow_events_activity_type ON workflow_run_events(activity_type);

-- ============================================================================
-- ACTIVITY EXECUTION TRACKING
-- ============================================================================

-- Track individual activity executions
CREATE TABLE IF NOT EXISTS workflow_activities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    
    -- Activity identification
    activity_id VARCHAR NOT NULL, -- Temporal activity ID
    activity_type VARCHAR NOT NULL, -- 'extract_ocr', 'chunk_document', etc.
    activity_name VARCHAR NOT NULL, -- Human-readable name
    
    -- Execution details
    task_queue VARCHAR NOT NULL, -- 'documents-queue'
    attempt_number INTEGER DEFAULT 1,
    
    -- Status
    status VARCHAR NOT NULL DEFAULT 'scheduled' CHECK (status IN (
        'scheduled', 'running', 'completed', 'failed', 'cancelled', 'timed_out'
    )),
    
    -- Timing
    scheduled_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    heartbeat_at TIMESTAMP WITH TIME ZONE, -- Last heartbeat
    
    -- Duration tracking
    duration_ms INTEGER GENERATED ALWAYS AS (
        EXTRACT(MILLISECONDS FROM (completed_at - started_at))
    ) STORED,
    
    -- Input/Output
    input_params JSONB,
    output_result JSONB,
    
    -- Error tracking
    error_message TEXT,
    error_type VARCHAR,
    is_retriable BOOLEAN DEFAULT true,
    
    -- Resource usage (optional)
    metadata JSONB, -- Can store: memory_used, cpu_percentage, etc.
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for activities
CREATE INDEX idx_workflow_activities_workflow_id ON workflow_activities(workflow_id);
CREATE INDEX idx_workflow_activities_activity_type ON workflow_activities(activity_type);
CREATE INDEX idx_workflow_activities_status ON workflow_activities(status);
CREATE INDEX idx_workflow_activities_scheduled_at ON workflow_activities(scheduled_at DESC);
CREATE INDEX idx_workflow_activities_duration ON workflow_activities(duration_ms);

-- ============================================================================
-- WORKFLOW SIGNALS & QUERIES
-- ============================================================================

-- Track signals sent to workflows
CREATE TABLE IF NOT EXISTS workflow_signals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    
    -- Signal details
    signal_name VARCHAR NOT NULL, -- 'document_received', 'ocr_complete', etc.
    signal_payload JSONB,
    
    -- Status
    status VARCHAR NOT NULL DEFAULT 'sent' CHECK (status IN (
        'sent', 'received', 'processed', 'failed'
    )),
    
    -- Timing
    sent_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    received_at TIMESTAMP WITH TIME ZONE,
    processed_at TIMESTAMP WITH TIME ZONE,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_workflow_signals_workflow_id ON workflow_signals(workflow_id);
CREATE INDEX idx_workflow_signals_name ON workflow_signals(signal_name);
CREATE INDEX idx_workflow_signals_status ON workflow_signals(status);

-- ============================================================================
-- SAGA PATTERN - COMPENSATION TRACKING
-- ============================================================================

-- Track compensating transactions for saga pattern
CREATE TABLE IF NOT EXISTS workflow_compensations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    
    -- Forward activity
    forward_activity_id UUID REFERENCES workflow_activities(id),
    forward_activity_type VARCHAR NOT NULL,
    
    -- Compensation activity
    compensation_activity_id UUID REFERENCES workflow_activities(id),
    compensation_activity_type VARCHAR NOT NULL,
    
    -- Status
    status VARCHAR NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending', 'executing', 'completed', 'failed', 'skipped'
    )),
    
    -- Execution tracking
    triggered_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    
    -- Results
    rollback_data JSONB, -- Data needed for rollback (e.g., entity IDs to delete)
    error_message TEXT,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_compensations_workflow_id ON workflow_compensations(workflow_id);
CREATE INDEX idx_compensations_status ON workflow_compensations(status);

-- ============================================================================
-- BATCH PROCESSING TRACKING
-- ============================================================================

-- Track batch processing for parallel execution
CREATE TABLE IF NOT EXISTS workflow_batches (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    activity_id UUID REFERENCES workflow_activities(id),
    
    -- Batch details
    batch_number INTEGER NOT NULL,
    total_batches INTEGER NOT NULL,
    
    -- Batch contents
    chunk_ids UUID[], -- Array of chunk IDs in this batch
    batch_size INTEGER NOT NULL, -- Token count or chunk count
    
    -- Status
    status VARCHAR NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending', 'processing', 'completed', 'failed', 'retrying'
    )),
    
    -- Timing
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    
    -- Results
    result JSONB,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE(workflow_id, batch_number)
);

CREATE INDEX idx_workflow_batches_workflow_id ON workflow_batches(workflow_id);
CREATE INDEX idx_workflow_batches_activity_id ON workflow_batches(activity_id);
CREATE INDEX idx_workflow_batches_status ON workflow_batches(status);

-- ============================================================================
-- WORKFLOW METRICS & ANALYTICS
-- ============================================================================

-- Aggregate metrics for workflow performance
CREATE TABLE IF NOT EXISTS workflow_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    
    -- Timing metrics
    total_duration_seconds INTEGER,
    ocr_duration_seconds INTEGER,
    normalization_duration_seconds INTEGER,
    entity_resolution_duration_seconds INTEGER,
    graph_construction_duration_seconds INTEGER,
    
    -- Activity counts
    total_activities INTEGER DEFAULT 0,
    successful_activities INTEGER DEFAULT 0,
    failed_activities INTEGER DEFAULT 0,
    retried_activities INTEGER DEFAULT 0,
    
    -- Processing metrics
    total_pages INTEGER,
    total_chunks INTEGER,
    total_batches INTEGER,
    entities_extracted INTEGER,
    relationships_extracted INTEGER,
    
    -- Cost tracking (optional)
    ocr_api_calls INTEGER DEFAULT 0,
    llm_api_calls INTEGER DEFAULT 0,
    estimated_cost_usd DECIMAL(10, 4),
    
    -- Quality metrics
    ocr_quality_score DECIMAL(3, 2), -- 0.00 to 1.00
    extraction_confidence DECIMAL(3, 2),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_workflow_metrics_workflow_id ON workflow_metrics(workflow_id);

-- ============================================================================
-- WORKFLOW RETRY & RECOVERY
-- ============================================================================

-- Track workflow retry attempts
CREATE TABLE IF NOT EXISTS workflow_retries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    
    -- Retry details
    retry_number INTEGER NOT NULL,
    retry_reason VARCHAR NOT NULL, -- 'activity_timeout', 'api_rate_limit', etc.
    
    -- What failed
    failed_activity_type VARCHAR,
    failed_at_phase VARCHAR,
    
    -- Recovery action
    recovery_action VARCHAR NOT NULL, -- 'retry_activity', 'restart_workflow', 'manual_intervention'
    
    -- Timing
    failed_at TIMESTAMP WITH TIME ZONE NOT NULL,
    retry_scheduled_at TIMESTAMP WITH TIME ZONE,
    retry_completed_at TIMESTAMP WITH TIME ZONE,
    
    -- Status
    status VARCHAR NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending', 'in_progress', 'succeeded', 'failed', 'abandoned'
    )),
    
    -- Backoff calculation
    backoff_seconds INTEGER,
    
    error_details JSONB,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_workflow_retries_workflow_id ON workflow_retries(workflow_id);
CREATE INDEX idx_workflow_retries_status ON workflow_retries(status);

-- ============================================================================
-- UPDATE EXISTING DOCUMENTS TABLE
-- ============================================================================

-- Add workflow tracking to documents table
ALTER TABLE documents 
ADD COLUMN IF NOT EXISTS current_workflow_id UUID REFERENCES workflows(id),
ADD COLUMN IF NOT EXISTS last_workflow_status VARCHAR,
ADD COLUMN IF NOT EXISTS workflow_progress_percentage INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS processing_started_at TIMESTAMP WITH TIME ZONE,
ADD COLUMN IF NOT EXISTS processing_completed_at TIMESTAMP WITH TIME ZONE;

CREATE INDEX idx_documents_workflow_id ON documents(current_workflow_id);
CREATE INDEX idx_documents_workflow_status ON documents(last_workflow_status);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_chunk_entity_chunk ON chunk_entity_mentions(chunk_id);
CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_chunk ON chunk_embeddings(chunk_id);
CREATE INDEX IF NOT EXISTS idx_document_entity_document ON document_entity_links(document_id);
CREATE INDEX IF NOT EXISTS idx_canonical_entities_key ON canonical_entities(entity_type, canonical_key);
CREATE INDEX IF NOT EXISTS idx_normalized_chunks_content_hash ON normalized_chunks(content_hash);
CREATE INDEX IF NOT EXISTS idx_normalized_chunks_pipeline_run ON normalized_chunks(pipeline_run_id);
