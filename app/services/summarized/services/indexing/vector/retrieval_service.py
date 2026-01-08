from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID
import re
from datetime import datetime

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_classic.retrievers.multi_query import MultiQueryRetriever
from langchain_core.documents import Document

from app.services.base_service import BaseService
from app.repositories.vector_embedding_repository import VectorEmbeddingRepository
from app.repositories.section_extraction_repository import SectionExtractionRepository
from app.services.summarized.services.indexing.vector.vector_template_service import VectorTemplateService
from app.services.summarized.services.indexing.vector.intent_classifier_service import IntentClassifierService
from app.services.summarized.services.indexing.vector.langchain_vector_store import BridgedVectorStore
from app.services.summarized.constants import (
    DOMAIN_KEYWORDS, 
    TERM_MAPPINGS, 
    QUERY_SECTION_MAPPINGS, 
    GENERAL_SECTION_BOOST
)
from app.core.config import settings
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class RetrievalService(BaseService):
    """Service for high-precision semantic retrieval of insurance documents.
    
    Integrated with LangChain for:
    1. Advanced query expansion via MultiQueryRetriever
    2. Standardized VectorStore interface via BridgedVectorStore
    3. Multi-stage retrieval and reranking
    """

    def __init__(self, session):
        """Initialize retrieval service with LangChain integration."""
        super().__init__(VectorEmbeddingRepository(session))
        self.vector_repo = self.repository
        self.section_repo = SectionExtractionRepository(session)
        self.template_service = VectorTemplateService()
        self.intent_classifier = IntentClassifierService()
        self.model_name = "all-MiniLM-L6-v2"
        
        # Lazy loaders for LangChain/ML components
        self._embeddings = None
        self._vector_store = None
        self._llm = None
        self._retriever = None
        
        # Insurance domain constants
        self.domain_keywords = DOMAIN_KEYWORDS
        self.term_mappings = TERM_MAPPINGS
        self.query_section_mappings = QUERY_SECTION_MAPPINGS
        self.general_section_boost = GENERAL_SECTION_BOOST

    @property
    def embeddings(self) -> HuggingFaceEmbeddings:
        """Lazy loader for HuggingFaceEmbeddings."""
        if self._embeddings is None:
            LOGGER.info(f"Loading embedding model: {self.model_name}")
            self._embeddings = HuggingFaceEmbeddings(model_name=self.model_name)
        return self._embeddings

    @property
    def vector_store(self) -> BridgedVectorStore:
        """Lazy loader for custom BridgedVectorStore."""
        if self._vector_store is None:
            self._vector_store = BridgedVectorStore(
                repository=self.vector_repo,
                embeddings=self.embeddings
            )
        return self._vector_store

    @property
    def llm(self) -> Any:
        """Lazy loader for configured LLM for query expansion."""
        if self._llm is None:
            if settings.llm_provider == "gemini":
                self._llm = ChatGoogleGenerativeAI(
                    model=settings.gemini_model,
                    google_api_key=settings.gemini_api_key,
                    temperature=0
                )
            else:
                from langchain_openai import ChatOpenAI
                self._llm = ChatOpenAI(
                    model=settings.openrouter_model,
                    openai_api_key=settings.openrouter_api_key,
                    openai_api_base=settings.openrouter_api_url.replace("/chat/completions", ""),
                    temperature=0
                )

        return self._llm

    def preprocess_query(self, query: str) -> str:
        """Preprocess query for better insurance domain understanding.
        
        Args:
            query: Raw query string
            
        Returns:
            Preprocessed query string
        """
        query = query.strip().lower()
        
        # Expand insurance abbreviations using whole-word matching
        for abbrev, expansions in self.term_mappings.items():
            pattern = rf"\b{re.escape(abbrev)}\b"
            if re.search(pattern, query, re.IGNORECASE):
                query = f"{query} {expansions[0]}"
        
        return query

    async def get_multi_query_retriever(self, **kwargs) -> MultiQueryRetriever:
        """Configure and return a MultiQueryRetriever with dynamic filters."""
        # Use our custom vector store as the base retriever
        base_retriever = self.vector_store.as_retriever(
            search_kwargs={"k": kwargs.get("top_k", 10), **kwargs}
        )
        
        return MultiQueryRetriever.from_llm(
            retriever=base_retriever,
            llm=self.llm,
        )

    def calculate_relevance_score(
        self,
        match_metadata: Dict[str, Any],
        query: str,
        cosine_score: float,
        filters: Optional[Dict[str, Any]] = None
    ) -> float:
        """Calculate comprehensive relevance score using multiple signals.
        
        Args:
            match_metadata: Metadata from the retrieved document
            query: Original query
            cosine_score: Base cosine similarity score (typically 0-1)
            filters: Applied filters
            
        Returns:
            Combined relevance score (0-1)
        """
        score = cosine_score
        query_lower = query.lower()
        
        # Boost 1: Query-specific section type relevance
        section_type = match_metadata.get("section_type")
        for query_term, section_boosts in self.query_section_mappings.items():
            if query_term in query_lower:
                boost = section_boosts.get(section_type, 0.0)
                score += boost
                if boost != 0:
                    LOGGER.debug(
                        f"Section boost applied: query_term='{query_term}', "
                        f"section='{section_type}', boost={boost}"
                    )
        
        # Boost 2: General section type importance (fallback)
        if section_type:
            score += self.general_section_boost.get(section_type, 0.0)
        
        # Boost 3: Keyword matching in searchable attributes
        searchable_text = []
        for key in ["section_type", "entity_type", "location_id", "workflow_type"]:
            val = match_metadata.get(key)
            if val:
                searchable_text.append(str(val))
        
        if searchable_text:
            combined_text = " ".join(searchable_text).lower()
            # Split query by spaces and common separators
            query_words = query_lower.replace("/", " ").replace("-", " ").split()
            keyword_matches = sum(1 for word in query_words 
                                 if len(word) > 2 and word in combined_text)
            
            # Additional exact term boosts
            if "policy" in query_lower and "policy" in combined_text:
                score += 0.05
            if "coverage" in query_lower and "coverage" in combined_text:
                score += 0.05
            
            score += keyword_matches * 0.03
        
        # Boost 4: Recency (if effective_date available)
        eff_date_str = match_metadata.get("effective_date")
        if eff_date_str:
            try:
                eff_date = datetime.strptime(eff_date_str.split()[0], "%Y-%m-%d").date()
                days_old = (datetime.now().date() - eff_date).days
                if days_old < 365:  # Within last year
                    recency_boost = 0.05 * (1 - days_old / 365)
                    score += recency_boost
            except (ValueError, TypeError, AttributeError):
                pass
        
        # Boost 5: Filter alignment
        if filters:
            if filters.get("document_id") == match_metadata.get("document_id"):
                score += 0.02
            if filters.get("section_type") == match_metadata.get("section_type"):
                score += 0.03
        
        return min(score, 1.0)

    async def run(
        self, 
        query: str, 
        top_k: int = 5,
        document_id: Optional[UUID] = None,
        section_type: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        use_query_expansion: bool = True,
        rerank: bool = True,
        include_entity_data: bool = True
    ) -> List[Dict[str, Any]]:
        """Retrieval with LangChain-driven multi-query expansion and reranking.
        
        Args:
            query: Natural language question or search term
            top_k: Number of final results to return
            document_id: Optional document scope filter
            section_type: Optional section type filter
            filters: Additional metadata filters
            use_query_expansion: Enable LangChain MultiQuery expansion
            rerank: Enable domain-specific reranking
            include_entity_data: Fetch actual entity data for results
            
        Returns:
            List of relevant results with scores and metadata
        """
        LOGGER.info(f"LangChain Retrieval query: '{query}' (top_k={top_k})")
        
        # Step 1: Preprocess query
        processed_query = self.preprocess_query(query)
        
        # Step 2: Intent classification for section filtering
        allowed_sections = None
        if not section_type:
            allowed_sections = self.intent_classifier.classify(processed_query)
        
        # Step 3: Configure filters
        search_kwargs = {}
        if document_id:
            search_kwargs["document_id"] = document_id
        search_kwargs["section_type"] = section_type or allowed_sections
        if filters:
            search_kwargs["filters"] = filters
            
        # Step 4: Retrieval (with optional expansion)
        docs = []
        if use_query_expansion:
            try:
                # Use MultiQueryRetriever
                retriever = await self.get_multi_query_retriever(
                    top_k=top_k * 5 if rerank else top_k,
                    **search_kwargs
                )
                # LangChain's MultiQueryRetriever handles variations and merging
                docs = await retriever.ainvoke(processed_query)
            except Exception as e:
                LOGGER.warning(f"MultiQueryRetriever failed, falling back to direct search: {e}")
                docs = await self.vector_store.asimilarity_search(
                    processed_query,
                    k=top_k * 5 if rerank else top_k,
                    **search_kwargs
                )
        else:
            # Direct similarity search via VectorStore
            docs = await self.vector_store.asimilarity_search(
                processed_query,
                k=top_k * 5 if rerank else top_k,
                **search_kwargs
            )

        # Step 5: Domain-specific Reranking
        scored_results = []
        if docs:
            query_vec = self.embeddings.embed_query(processed_query)

        for doc in docs:
            # Base similarity score
            # Use the repository directly for efficiency
            matches = await self.vector_repo.get_embeddings_with_distance(
                embedding=query_vec,
                document_id=UUID(doc.metadata["document_id"]),
                section_type=doc.metadata["section_type"],
                entity_id=doc.metadata["entity_id"],
                max_distance=1.0, # High threshold to ensure we get a score
                limit=1
            )
            
            # Get the score from the matched entity
            base_score = 0.0
            if matches:
                _, dist = matches[0]
                base_score = max(0, 1.0 - float(dist))
            
            # Calculate final domain-weighted score
            final_score = self.calculate_relevance_score(
                match_metadata=doc.metadata,
                query=query,
                cosine_score=base_score,
                filters={'document_id': document_id, 'section_type': section_type}
            )
            scored_results.append((doc, final_score))
            
        # Sort by final score
        scored_results.sort(key=lambda x: x[1], reverse=True)
        final_docs = scored_results[:top_k]
        
        # Step 6: Format results
        results = []
        for doc, score in final_docs:
            metadata = doc.metadata
            entity_id = metadata["entity_id"]
            section_type_attr = metadata["section_type"]
            document_id_attr = UUID(metadata["document_id"])
            
            # Fetch content preview and entity data
            evidence = await self._get_content_preview_from_metadata(metadata)
            
            entity_data = None
            if include_entity_data:
                entity_data = await self._fetch_entity_data_from_metadata(metadata)

            results.append({
                "document_id": str(document_id_attr),
                "section_type": section_type_attr or "unknown",
                "entity_type": metadata.get("entity_type") or "unknown",
                "entity_id": entity_id,
                "relevance_score": score,
                "metadata": metadata,
                "answer": entity_data,
                "evidence": evidence,
                "confidence": "high" if score > 0.8 else "medium" if score > 0.6 else "low",
                "entity_data": entity_data,
            })
        
        LOGGER.info(f"Returning {len(results)} LangChain-optimized results")
        return results

    async def _fetch_entity_data_from_metadata(self, metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Adapter to fetch entity data from metadata dict."""
        # Create a mock match object to satisfy existing _fetch_entity_data interface
        class MockMatch:
            def __init__(self, m):
                self.section_type = m.get("section_type")
                self.entity_id = m.get("entity_id")
                self.document_id = UUID(m.get("document_id"))
                self.workflow_type = m.get("workflow_type")
        
        return await self._fetch_entity_data(MockMatch(metadata))

    async def _get_content_preview_from_metadata(self, metadata: Dict[str, Any]) -> Optional[str]:
        """Adapter to fetch content preview from metadata dict."""
        class MockMatch:
            def __init__(self, m):
                self.section_type = m.get("section_type")
                self.entity_id = m.get("entity_id")
                self.document_id = UUID(m.get("document_id"))
                self.workflow_type = m.get("workflow_type")
                
        return await self._get_content_preview(MockMatch(metadata))

    async def _fetch_entity_data(self, match: Any) -> Optional[Dict[str, Any]]:
        """Fetch the actual extracted entity data for a match from section extractions."""
        try:
            section_type = match.section_type
            entity_id = match.entity_id
            document_id = match.document_id
            
            sections = await self.section_repo.get_by_document(
                document_id, 
                UUID(match.workflow_type) if match.workflow_type and match.workflow_type != "None" else None, 
                section_type
            )
            
            if not sections:
                # Fallback: get by document_id and section_type
                from sqlalchemy import select
                from app.database.models import SectionExtraction
                stmt = select(SectionExtraction).where(
                    SectionExtraction.document_id == document_id,
                    SectionExtraction.section_type == section_type
                )
                res = await self.repository.session.execute(stmt)
                sections = list(res.scalars().all())

            if not sections:
                return None

            section = sections[0]
            data = section.extracted_fields

            if entity_id.endswith("_section_root"):
                return data

            # Logic for list-based entities
            mapping = {
                "coverages": "coverages",
                "loss_run": "claims",
                "schedule_of_values": "locations",
                "endorsements": "endorsements",
                "exclusions": "exclusions",
                "definitions": "definitions",
                "vehicle_schedule": "vehicles",
                "driver_schedule": "drivers"
            }
            
            list_key = mapping.get(section_type.lower())
            if list_key and list_key in data:
                idx_str = entity_id.split("_")[-1]
                if idx_str.isdigit():
                    idx = int(idx_str)
                    if 0 <= idx < len(data[list_key]):
                        return data[list_key][idx]

            return data
            
        except Exception as e:
            LOGGER.warning(f"Failed to fetch entity data: {e}")
        
        return None

    async def _get_content_preview(self, match: Any, max_chars: int = 500) -> Optional[str]:
        """Extract content preview from match by regenerating template."""
        try:
            entity_data = await self._fetch_entity_data(match)
            if not entity_data:
                return f"Section: {match.section_type} | ID: {match.entity_id}"

            preview = await self.template_service.run(match.section_type, entity_data)
            
            if preview and len(preview) > max_chars:
                preview = preview[:max_chars] + "..."
            
            return preview
        except Exception as e:
            LOGGER.warning(f"Failed to generate content preview: {e}")
            return f"Section: {match.section_type} | ID: {match.entity_id}"