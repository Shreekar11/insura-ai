"""
Query Understanding Service - Stage 1 Orchestrator

Coordinates the query understanding pipeline:
1. Intent classification (QA, ANALYSIS, AUDIT)
2. Entity extraction (policy numbers, dates, coverage types)
3. Query expansion (insurance abbreviations)
4. Section/entity type filtering
5. Workflow context retrieval
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.step_repository import (
    StepEntityOutputRepository,
    StepSectionOutputRepository,
)
from app.repositories.workflow_repository import WorkflowDocumentRepository
from app.schemas.query import QueryPlan, WorkflowContext
from app.services.retrieval.constants import VALID_ENTITY_TYPES, VALID_SECTION_TYPES
from app.services.retrieval.query_understanding.entity_extractor import (
    EntityExtractor,
)
from app.services.retrieval.query_understanding.intent_classifier import (
    IntentClassifier,
)
from app.services.retrieval.query_understanding.query_expander import QueryExpander
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class QueryUnderstandingService:
    """
    Service for understanding and planning user queries (Stage 1).

    Coordinates intent classification, entity extraction, query expansion,
    and workflow context retrieval to produce a comprehensive QueryPlan.
    """

    def __init__(self, db_session: AsyncSession):
        """
        Initialize query understanding service.

        Args:
            db_session: SQLAlchemy async session for database access
        """
        self.db_session = db_session
        self.intent_classifier = IntentClassifier()
        self.entity_extractor = EntityExtractor()
        self.query_expander = QueryExpander()

        # Repository initialization
        self.section_repo = StepSectionOutputRepository(db_session)
        self.entity_repo = StepEntityOutputRepository(db_session)
        self.workflow_doc_repo = WorkflowDocumentRepository(db_session)

    async def understand_query(
        self,
        query: str,
        workflow_id: UUID,
        target_document_ids: list[UUID] | None = None,
    ) -> QueryPlan:
        """
        Understand user query and create comprehensive query plan.

        Args:
            query: User's natural language question
            workflow_id: Workflow to search within
            target_document_ids: Specific documents to query (None = all workflow docs)

        Returns:
            QueryPlan with intent, entities, expansions, and context
        """
        LOGGER.info(
            "Starting query understanding",
            extra={
                "query": query[:100],
                "workflow_id": str(workflow_id),
                "target_documents": len(target_document_ids) if target_document_ids else "all",
            },
        )

        # Step 1: Classify intent
        intent, confidence, traversal_depth = self.intent_classifier.classify(query)
        LOGGER.info(
            "Intent classified",
            extra={
                "intent": intent,
                "confidence": confidence,
                "traversal_depth": traversal_depth,
            },
        )

        # Step 2: Extract entities
        extracted_entities = self.entity_extractor.extract(query)
        LOGGER.info(
            "Entities extracted",
            extra={
                "policy_numbers": len(extracted_entities.policy_numbers),
                "coverage_types": len(extracted_entities.coverage_types),
                "entity_names": len(extracted_entities.entity_names),
                "dates": len(extracted_entities.dates),
                "amounts": len(extracted_entities.amounts),
                "locations": len(extracted_entities.locations),
                "section_hints": len(extracted_entities.section_hints),
            },
        )

        # Step 3: Expand query
        expanded_queries = self.query_expander.expand(query)
        LOGGER.info(
            "Query expanded",
            extra={"expansions_count": len(expanded_queries)},
        )

        # Step 4: Fetch workflow context
        workflow_context = await self._fetch_workflow_context(
            workflow_id, target_document_ids
        )
        LOGGER.info(
            "Workflow context fetched",
            extra={
                "document_count": workflow_context.document_count,
                "sections_count": len(workflow_context.sections),
                "entities_count": len(workflow_context.entities),
            },
        )

        # Step 5: Derive section and entity type filters
        section_type_filters = self._derive_section_filters(
            extracted_entities.section_hints, intent
        )
        entity_type_filters = self._derive_entity_filters(
            extracted_entities.coverage_types, intent
        )

        LOGGER.info(
            "Filters derived",
            extra={
                "section_filters": section_type_filters,
                "entity_filters": entity_type_filters,
            },
        )

        # Step 6: Build QueryPlan
        query_plan = QueryPlan(
            original_query=query,
            intent=intent,
            traversal_depth=traversal_depth,
            extracted_entities=extracted_entities,
            expanded_queries=expanded_queries,
            workflow_context=workflow_context,
            target_document_ids=target_document_ids,
            section_type_filters=section_type_filters,
            entity_type_filters=entity_type_filters,
        )

        LOGGER.info(
            "Query plan created",
            extra={
                "intent": intent,
                "traversal_depth": traversal_depth,
                "expanded_queries": len(expanded_queries),
                "section_filters": len(section_type_filters),
                "entity_filters": len(entity_type_filters),
            },
        )

        return query_plan

    async def _fetch_workflow_context(
        self, workflow_id: UUID, target_document_ids: list[UUID] | None
    ) -> WorkflowContext:
        """
        Fetch workflow context (sections, entities, documents) from PostgreSQL.

        Args:
            workflow_id: Workflow to fetch context for
            target_document_ids: Specific documents to include (None = all)

        Returns:
            WorkflowContext with sections, entities, and document IDs
        """
        # Fetch all documents in the workflow
        workflow_docs = await self.workflow_doc_repo.get_by_workflow_id(workflow_id)

        if not workflow_docs:
            LOGGER.warning(
                "No documents found for workflow",
                extra={"workflow_id": str(workflow_id)},
            )
            return WorkflowContext(
                workflow_id=workflow_id,
                sections=[],
                entities=[],
                document_ids=[],
                document_count=0,
            )

        # Filter to target documents if specified
        if target_document_ids:
            document_ids = [
                wd.document_id
                for wd in workflow_docs
                if wd.document_id in target_document_ids
            ]
        else:
            document_ids = [wd.document_id for wd in workflow_docs]

        # Fetch all sections and entities for these documents
        all_sections = []
        all_entities = []

        for doc_id in document_ids:
            # Fetch sections for this document
            sections = await self.section_repo.get_by_document_and_workflow(
                doc_id, workflow_id
            )
            all_sections.extend(
                [
                    {
                        "id": str(section.id),
                        "document_id": str(section.document_id),
                        "section_type": section.section_type,
                        "section_name": section.section_type,
                        "content": section.display_payload,
                        "page_numbers": [section.page_range.get("start")] if section.page_range and "start" in section.page_range else [],
                    }
                    for section in sections
                ]
            )

            # Fetch entities for this document
            entities = await self.entity_repo.get_by_document_and_workflow(
                doc_id, workflow_id
            )
            all_entities.extend(
                [
                    {
                        "id": str(entity.id),
                        "document_id": str(entity.document_id),
                        "entity_type": entity.entity_type,
                        "entity_name": entity.entity_label,
                        "attributes": entity.display_payload,
                        "confidence": float(entity.confidence) if entity.confidence else None,
                    }
                    for entity in entities
                ]
            )

        return WorkflowContext(
            workflow_id=workflow_id,
            sections=all_sections,
            entities=all_entities,
            document_ids=document_ids,
            document_count=len(document_ids),
        )

    def _derive_section_filters(
        self, section_hints: list[str], intent: str
    ) -> list[str]:
        """
        Derive section type filters from extracted hints and intent.

        Args:
            section_hints: Section hints from entity extraction
            intent: Query intent (QA, ANALYSIS, AUDIT)

        Returns:
            List of valid section types to prioritize
        """
        filters = []

        # Add hints from extraction
        filters.extend(section_hints)

        # Add intent-based defaults (from INTENT_SECTION_BOOSTS)
        if intent == "QA":
            filters.extend(["declarations", "coverages", "schedule"])
        elif intent == "ANALYSIS":
            filters.extend(["coverages", "endorsements", "exclusions", "conditions"])
        elif intent == "AUDIT":
            filters.extend(["endorsements", "loss_run", "claims", "conditions"])

        # Deduplicate and validate
        valid_filters = list(
            set(f for f in filters if f in VALID_SECTION_TYPES)
        )

        return valid_filters

    def _derive_entity_filters(
        self, coverage_types: list[str], intent: str
    ) -> list[str]:
        """
        Derive entity type filters from extracted coverage types and intent.

        Args:
            coverage_types: Extracted coverage types
            intent: Query intent (QA, ANALYSIS, AUDIT)

        Returns:
            List of valid entity types to prioritize
        """
        filters = []

        # If coverage types are mentioned, prioritize coverage entities
        if coverage_types:
            filters.append("coverage")

        # Add intent-based defaults
        if intent == "QA":
            filters.extend(["policy", "organization", "coverage"])
        elif intent == "ANALYSIS":
            filters.extend(["coverage", "endorsement", "exclusion", "condition"])
        elif intent == "AUDIT":
            filters.extend(["endorsement", "claim", "coverage"])

        # Deduplicate and validate
        valid_filters = list(
            set(f for f in filters if f in VALID_ENTITY_TYPES)
        )

        return valid_filters
