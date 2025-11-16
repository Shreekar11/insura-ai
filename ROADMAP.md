# Insura-AI Development Roadmap

## Current State Assessment

### ✅ Completed
1. **Basic OCR Implementation**
   - Mistral OCR service (`app/services/mistral_ocr.py`)
   - OCR API endpoint at `/api/v1/ocr/extract`
   - Base OCR interface for pluggable implementations
   - Error handling and retry logic
   - Returns: `OCRResult` with text, confidence, metadata, layout

### ❌ Not Yet Implemented
1. **OCR Data Quality & Normalization** - No cleanup/normalization layer
2. **Database Layer** - No database models or persistence
3. **Document Classification** - No classification service
4. **Temporal Workflows** - No workflow orchestration

---

## Implementation Roadmap

### 📋 Step 1: Validate & Improve OCR Output (Data Quality First)

**Priority: CRITICAL** ⚠️  
**Estimated Time: 3-5 days**

#### Why This Must Come First
- OCR output is the foundation for all downstream processing
- Poor quality OCR → poor classification accuracy
- Clean data enables reliable database storage and analytics

#### Implementation Tasks

##### 1.1 Create OCR Normalization Service
**File**: `app/services/ocr_normalizer.py`

**Responsibilities**:
- Clean extracted text (remove noise, garbage tokens)
- Normalize dates to `YYYY-MM-DD` format
- Clean currency values → decimals only
- Normalize phone numbers (standardize format)
- Normalize email addresses
- Remove/fix OCR artifacts (garbled characters, misreads)

**Key Functions**:
```python
class OCRNormalizer:
    def normalize_text(self, raw_text: str) -> str:
        """Remove noise and clean text"""
    
    def normalize_date(self, date_str: str) -> str:
        """Convert various date formats to YYYY-MM-DD"""
    
    def normalize_currency(self, value_str: str) -> float:
        """Extract and normalize currency to decimal"""
    
    def normalize_phone(self, phone_str: str) -> str:
        """Standardize phone number format"""
    
    def extract_fields(self, text: str) -> Dict[str, Any]:
        """Extract structured fields (policy number, dates, amounts)"""
```

##### 1.2 Add Field Extraction Logic
**File**: `app/services/field_extractor.py`

**Responsibilities**:
- Extract insurance-specific fields:
  - Policy numbers (pattern matching)
  - Coverage types
  - Effective dates / Expiration dates
  - Premium amounts
  - Insured party information
  - Claim numbers
  - Submission IDs

##### 1.3 Integrate Normalization into OCR Flow
**Update**: `app/api/v1/endpoints/ocr.py`

- Add normalization step after OCR extraction
- Return both raw and normalized text
- Include extracted fields in response

##### 1.4 Add Data Quality Metrics
**File**: `app/services/quality_checker.py`

**Metrics to Track**:
- Text confidence scores
- Missing critical fields
- Formatting issues detected
- Normalization warnings

#### Dependencies to Add
```toml
# Add to pyproject.toml
dateparser>=1.2.0  # Date parsing
phonenumbers>=8.13.0  # Phone normalization
regex>=2023.12.25  # Advanced pattern matching
```

#### Testing Requirements
- Test with various date formats (US, EU, ISO)
- Test currency extraction ($1,234.56, USD 1234.56, etc.)
- Test phone number formats (international, US)
- Test field extraction on sample insurance documents

---

### 📋 Step 2: Insert Clean OCR Results Into Database

**Priority: HIGH**  
**Estimated Time: 5-7 days**

#### Why This Comes Second
- Database becomes single source of truth
- Enables retry mechanisms for classification
- Foundation for analytics and auditing

#### Implementation Tasks

##### 2.1 Database Setup
**Add Dependencies**:
```toml
# Add to pyproject.toml
sqlalchemy>=2.0.23
alembic>=1.13.1  # Database migrations
asyncpg>=0.29.0  # PostgreSQL async driver (or use your preferred DB)
psycopg2-binary>=2.9.9  # PostgreSQL sync driver (for migrations)
```

**File**: `app/database/__init__.py`
**File**: `app/database/base.py` - Database engine and session management
**File**: `app/database/session.py` - Async database session dependency

##### 2.2 Database Models
**File**: `app/database/models.py` or `app/database/models/`

**Tables to Create**:

1. **`documents`**
```python
- id: UUID (primary key)
- original_url: String
- file_name: String
- file_type: String (pdf, image, etc.)
- file_size: Integer
- status: String (pending, processing, completed, failed)
- created_at: DateTime
- updated_at: DateTime
- processed_at: DateTime (nullable)
```

2. **`document_pages`**
```python
- id: UUID (primary key)
- document_id: UUID (foreign key → documents.id)
- page_number: Integer
- raw_text: Text (raw OCR output)
- normalized_text: Text (cleaned/normalized)
- confidence_score: Float
- page_metadata: JSON (layout info, bounding boxes, etc.)
- created_at: DateTime
```

3. **`document_raw_text`** (alternative: store in document_pages.raw_text)
```python
- id: UUID (primary key)
- document_id: UUID (foreign key)
- page_id: UUID (foreign key → document_pages.id, nullable)
- full_text: Text (combined text across all pages)
- raw_text: Text (original OCR output before normalization)
- created_at: DateTime
```

4. **`extracted_fields`**
```python
- id: UUID (primary key)
- document_id: UUID (foreign key)
- page_id: UUID (foreign key, nullable)
- field_name: String (policy_number, effective_date, premium_amount, etc.)
- field_value: String (normalized value)
- raw_value: String (original extracted value)
- confidence: Float
- field_type: String (date, currency, text, number, etc.)
- created_at: DateTime
```

##### 2.3 Database Service Layer
**File**: `app/services/document_service.py`

**Responsibilities**:
```python
class DocumentService:
    async def create_document(self, url: str, metadata: Dict) -> Document:
        """Create document record"""
    
    async def save_ocr_result(
        self, 
        document_id: UUID, 
        ocr_result: OCRResult,
        normalized_text: str,
        extracted_fields: Dict[str, Any]
    ) -> None:
        """Save OCR results to database"""
    
    async def get_document(self, document_id: UUID) -> Document:
        """Retrieve document with pages and fields"""
    
    async def update_document_status(
        self, 
        document_id: UUID, 
        status: str
    ) -> None:
        """Update document processing status"""
```

##### 2.4 Update OCR Endpoint
**Update**: `app/api/v1/endpoints/ocr.py`

- Save OCR results to database after normalization
- Return document_id from database (not generated UUID)
- Add endpoint to retrieve document: `GET /api/v1/documents/{document_id}`

##### 2.5 Database Configuration
**Update**: `app/config.py`

Add database settings:
```python
# Database Settings
database_url: str = "postgresql+asyncpg://user:pass@localhost/insura_ai"
database_pool_size: int = 10
database_max_overflow: int = 20
database_echo: bool = False  # SQL query logging
```

##### 2.6 Database Migrations
**File**: `alembic.ini` (generated)
**Directory**: `alembic/versions/`

- Create initial migration for all tables
- Set up Alembic for version control

#### Testing Requirements
- Test document creation and retrieval
- Test page storage with OCR results
- Test field extraction and storage
- Test concurrent document processing
- Test database rollback on errors

---

### 📋 Step 3: Build Classification Layer Using Mistral Classifier Factory

**Priority: HIGH**  
**Estimated Time: 7-10 days**

#### Why This Comes After Database
- Classification needs clean, normalized text from database
- Enables retry mechanisms using stored documents
- Can build training datasets from stored OCR results

#### Implementation Tasks

##### 3.1 Document Classification Service
**File**: `app/services/document_classifier.py`

**Responsibilities**:
- Integrate with Mistral Classifier Factory API
- Classify documents into types:
  - Policy
  - Claim
  - Quote
  - Submission
  - Proposal
  - Audit Packet
  - SOV (Statement of Values)
  - Others

**Key Functions**:
```python
class DocumentClassifier:
    async def classify_document(
        self, 
        document_text: str,
        document_id: UUID
    ) -> ClassificationResult:
        """Classify document using Mistral Classifier Factory"""
    
    async def classify_with_fallback(
        self,
        document_text: str,
        confidence_threshold: float = 0.8
    ) -> ClassificationResult:
        """Classify with LLM fallback for low confidence"""
```

##### 3.2 Classification Result Model
**File**: `app/api/v1/models/classification.py`

```python
class ClassificationResult(BaseModel):
    document_type: str  # Policy, Claim, Quote, etc.
    confidence: float  # 0.0 to 1.0
    classification_method: str  # "mistral_classifier" or "llm_fallback"
    alternatives: List[Dict[str, float]]  # Alternative classifications
    requires_review: bool  # Flag for manual review
```

##### 3.3 Confidence Threshold Configuration
**Update**: `app/config.py`

```python
# Classification Settings
classifier_high_confidence_threshold: float = 0.85
classifier_medium_confidence_threshold: float = 0.65
classifier_low_confidence_threshold: float = 0.50
enable_llm_fallback: bool = True
llm_fallback_provider: str = "claude"  # or "gpt"
```

##### 3.4 LLM Fallback Service
**File**: `app/services/llm_classifier.py`

**Responsibilities**:
- Fallback classification using Claude/GPT when Mistral confidence is low
- Provide structured prompt for document classification
- Parse LLM response into ClassificationResult

##### 3.5 Update Database Models
**Add to**: `app/database/models.py`

**New Table: `document_classifications`**
```python
- id: UUID (primary key)
- document_id: UUID (foreign key)
- document_type: String
- confidence: Float
- classification_method: String
- alternatives_json: JSON
- requires_review: Boolean
- reviewed_at: DateTime (nullable)
- reviewed_by: String (nullable)
- created_at: DateTime
```

##### 3.6 Classification Endpoint
**File**: `app/api/v1/endpoints/classification.py`

**Endpoints**:
- `POST /api/v1/classify/{document_id}` - Classify existing document
- `GET /api/v1/classify/{document_id}` - Get classification result
- `POST /api/v1/classify/batch` - Batch classification

##### 3.7 Integration with OCR Flow
**Update**: `app/api/v1/endpoints/ocr.py`

- Optional: Add classification step after OCR + DB save
- Make it configurable (sync vs async classification)

#### Dependencies to Add
```toml
# Add to pyproject.toml (if using Claude/GPT for fallback)
anthropic>=0.18.0  # Claude API
openai>=1.12.0  # GPT API (alternative)
```

#### Training Data Requirements
- **30-100 labeled samples per document type**
- Store labeled samples in database
- Create training data export functionality
- Support incremental model updates

#### Testing Requirements
- Test classification with sample documents
- Test confidence threshold logic
- Test LLM fallback mechanism
- Test batch classification
- Validate classification accuracy metrics

---

### 📋 Step 4: Implement Temporal Workflows

**Priority: MEDIUM** (after classification works)  
**Estimated Time: 10-14 days**

#### Why This Comes Last
- Workflows orchestrate the entire pipeline
- Need all components (OCR, DB, Classification) working first
- Temporal enables reliability, retries, and observability

#### Implementation Tasks

##### 4.1 Temporal Setup
**Add Dependencies**:
```toml
# Add to pyproject.toml
temporalio>=1.7.0
```

**File**: `app/workflows/__init__.py`
**File**: `app/workflows/config.py` - Temporal connection settings

##### 4.2 Workflow Definitions

**File**: `app/workflows/document_processing_workflow.py`

**Main Workflow: `DocumentProcessingWorkflow`**

```python
@workflow.defn
class DocumentProcessingWorkflow:
    @workflow.run
    async def run(self, document_url: str) -> WorkflowResult:
        """
        Orchestrates the complete document processing pipeline:
        
        1. OCR extraction
        2. Data normalization
        3. Save to database
        4. Document classification
        5. Route to appropriate workflow based on classification
        """
```

**Workflow Steps**:
1. **OCR Activity**: Extract text from document
2. **Normalization Activity**: Clean and normalize OCR output
3. **Database Save Activity**: Store results in database
4. **Classification Activity**: Classify document type
5. **Routing Activity**: Route to specific workflow based on type

**File**: `app/workflows/activities/document_activities.py`

```python
# Activities (synchronous operations)
@activity.defn
async def extract_ocr_activity(url: str) -> OCRResult:
    """OCR extraction activity"""

@activity.defn
async def normalize_text_activity(raw_text: str) -> NormalizedResult:
    """Text normalization activity"""

@activity.defn
async def save_to_db_activity(...) -> UUID:
    """Database save activity"""

@activity.defn
async def classify_document_activity(...) -> ClassificationResult:
    """Document classification activity"""
```

##### 4.3 Domain-Specific Workflows

**File**: `app/workflows/policy_workflow.py`
```python
@workflow.defn
class PolicyComparisonWorkflow:
    """Workflow for policy document processing"""
```

**File**: `app/workflows/claim_workflow.py`
```python
@workflow.defn
class ClaimsIntakeWorkflow:
    """Workflow for claim document processing"""
```

**File**: `app/workflows/quote_workflow.py`
```python
@workflow.defn
class QuoteCompareWorkflow:
    """Workflow for quote document processing"""
```

**File**: `app/workflows/submission_workflow.py`
```python
@workflow.defn
class SubmissionWorkflow:
    """Workflow for submission document processing"""
```

##### 4.4 Temporal Worker
**File**: `app/workflows/worker.py`

```python
async def run_worker():
    """Run Temporal worker to process workflows"""
    client = await Client.connect("localhost:7233")
    
    worker = Worker(
        client,
        task_queue="document-processing",
        workflows=[DocumentProcessingWorkflow, ...],
        activities=[...],
    )
    
    await worker.run()
```

##### 4.5 Workflow API Endpoints
**File**: `app/api/v1/endpoints/workflows.py`

**Endpoints**:
- `POST /api/v1/workflows/process` - Start document processing workflow
- `GET /api/v1/workflows/{workflow_id}` - Get workflow status
- `GET /api/v1/workflows/{workflow_id}/result` - Get workflow result
- `POST /api/v1/workflows/cancel/{workflow_id}` - Cancel workflow

##### 4.6 Workflow Configuration
**Update**: `app/config.py`

```python
# Temporal Settings
temporal_host: str = "localhost"
temporal_port: int = 7233
temporal_namespace: str = "default"
temporal_task_queue: str = "document-processing"
```

##### 4.7 Error Handling & Retries
- Configure retry policies for activities
- Handle workflow failures gracefully
- Support workflow resumption from last successful step
- Dead letter queue for failed workflows

#### Testing Requirements
- Test workflow execution end-to-end
- Test workflow retry mechanisms
- Test workflow cancellation
- Test concurrent workflow execution
- Test workflow failure recovery

---

## Project Structure (Final State)

```
insura-ai/
├── app/
│   ├── api/
│   │   └── v1/
│   │       ├── endpoints/
│   │       │   ├── ocr.py (✅ exists, needs normalization integration)
│   │       │   ├── documents.py (NEW - document CRUD)
│   │       │   ├── classification.py (NEW)
│   │       │   └── workflows.py (NEW)
│   │       └── models/
│   │           ├── ocr.py (✅ exists)
│   │           ├── documents.py (NEW)
│   │           ├── classification.py (NEW)
│   │           └── workflows.py (NEW)
│   ├── database/
│   │   ├── __init__.py (NEW)
│   │   ├── base.py (NEW)
│   │   ├── session.py (NEW)
│   │   ├── models.py (NEW - all DB models)
│   │   └── alembic/ (NEW - migrations)
│   ├── services/
│   │   ├── ocr_base.py (✅ exists)
│   │   ├── mistral_ocr.py (✅ exists)
│   │   ├── ocr_normalizer.py (NEW - Step 1)
│   │   ├── field_extractor.py (NEW - Step 1)
│   │   ├── quality_checker.py (NEW - Step 1)
│   │   ├── document_service.py (NEW - Step 2)
│   │   ├── document_classifier.py (NEW - Step 3)
│   │   └── llm_classifier.py (NEW - Step 3)
│   ├── workflows/
│   │   ├── __init__.py (NEW)
│   │   ├── config.py (NEW)
│   │   ├── worker.py (NEW)
│   │   ├── document_processing_workflow.py (NEW - Step 4)
│   │   ├── policy_workflow.py (NEW - Step 4)
│   │   ├── claim_workflow.py (NEW - Step 4)
│   │   ├── quote_workflow.py (NEW - Step 4)
│   │   ├── submission_workflow.py (NEW - Step 4)
│   │   └── activities/
│   │       └── document_activities.py (NEW - Step 4)
│   ├── config.py (✅ exists, needs DB/Temporal config)
│   └── main.py (✅ exists)
├── tests/
│   ├── test_ocr_normalizer.py (NEW - Step 1)
│   ├── test_document_service.py (NEW - Step 2)
│   ├── test_classifier.py (NEW - Step 3)
│   └── test_workflows.py (NEW - Step 4)
├── pyproject.toml (✅ exists, needs new deps)
└── ROADMAP.md (✅ this file)
```

---

## Implementation Order Summary

```
[✅ OCR Basic Implementation] ← CURRENT STATE
      ↓
[Step 1] OCR Normalization & Quality
      ↓
[Step 2] Database Layer & Persistence
      ↓
[Step 3] Document Classification
      ↓
[Step 4] Temporal Workflows
      ↓
[✅ Complete Pipeline]
```

---

## Critical Dependencies to Add

### Step 1
- `dateparser>=1.2.0`
- `phonenumbers>=8.13.0`
- `regex>=2023.12.25`

### Step 2
- `sqlalchemy>=2.0.23`
- `alembic>=1.13.1`
- `asyncpg>=0.29.0` (or your preferred async DB driver)
- `psycopg2-binary>=2.9.9` (for migrations)

### Step 3
- `anthropic>=0.18.0` (optional - for Claude fallback)
- `openai>=1.12.0` (optional - for GPT fallback)

### Step 4
- `temporalio>=1.7.0`

---

## Success Metrics

### Step 1: OCR Quality
- ✅ Date normalization accuracy > 95%
- ✅ Currency extraction accuracy > 98%
- ✅ Field extraction coverage > 90% of critical fields

### Step 2: Database
- ✅ Document persistence success rate > 99%
- ✅ Query response time < 100ms for single document retrieval
- ✅ Support concurrent processing (10+ simultaneous documents)

### Step 3: Classification
- ✅ Classification accuracy > 85% on high-confidence predictions
- ✅ < 20% of documents require manual review
- ✅ LLM fallback improves low-confidence classifications by 30%+

### Step 4: Workflows
- ✅ End-to-end workflow completion rate > 95%
- ✅ Workflow retry success rate > 80%
- ✅ Average workflow duration < 5 minutes for typical documents

---

## Next Immediate Actions

1. **Start with Step 1** - Create `app/services/ocr_normalizer.py`
2. **Set up development database** - Install PostgreSQL (or preferred DB)
3. **Create initial test documents** - Gather 10-20 sample insurance documents for testing
4. **Set up Temporal server** - For Step 4 (can be done later, but good to have dev environment ready)

---

## Notes

- Follow TDD principles: Write tests first for each step
- Maintain code style per `.cursor/rules/code-style.mdc`
- Use FastAPI best practices per `.cursor/rules/fastapi.mdc`
- All services should be testable with dependency injection
- Use async/await throughout for scalability

