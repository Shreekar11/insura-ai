"""Document profile builder service.

This service aggregates page classifications into a document-level profile,
replacing the need for Tier 1 LLM classification. It derives:
- Document type from page type distribution
- Section boundaries from consecutive page type runs
- Page-to-section mapping for downstream processing
"""

from typing import List, Dict, Optional, Tuple
from uuid import UUID
from collections import Counter

from app.models.page_analysis_models import (
    PageClassification,
    PageType,
    DocumentType,
    DocumentProfile,
    SectionBoundary,
)
from app.utils.section_type_mapper import SectionTypeMapper
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)

# Singleton instance
_document_profile_builder_instance: Optional["DocumentProfileBuilder"] = None


class DocumentProfileBuilder:
    """Builds document profiles from page classifications.
    
    This service aggregates page-level classifications into a coherent
    document profile, enabling downstream workflows to understand document
    structure without additional LLM calls.
    
    The builder:
    1. Analyzes page type distribution to determine document type
    2. Detects section boundaries from consecutive page type runs
    3. Creates a page-to-section mapping for chunking and extraction
    """
    
    # Mapping from dominant page types to document types
    PAGE_TO_DOCUMENT_TYPE: Dict[PageType, DocumentType] = {
        PageType.DECLARATIONS: DocumentType.POLICY,
        PageType.COVERAGES: DocumentType.POLICY,
        PageType.CONDITIONS: DocumentType.POLICY,
        PageType.EXCLUSIONS: DocumentType.POLICY,
        PageType.ENDORSEMENT: DocumentType.ENDORSEMENT,
        PageType.SOV: DocumentType.SOV,
        PageType.LOSS_RUN: DocumentType.LOSS_RUN,
        PageType.INVOICE: DocumentType.INVOICE,
        PageType.DEFINITIONS: DocumentType.POLICY,
        PageType.TABLE_OF_CONTENTS: DocumentType.POLICY,
        PageType.BOILERPLATE: DocumentType.UNKNOWN,
        PageType.DUPLICATE: DocumentType.UNKNOWN,
        PageType.UNKNOWN: DocumentType.UNKNOWN,
    }
    
    # Document type inference rules based on page type presence
    DOCUMENT_TYPE_RULES: List[Tuple[List[PageType], DocumentType, float]] = [
        # If has declarations AND coverages -> policy (high confidence)
        ([PageType.DECLARATIONS, PageType.COVERAGES], DocumentType.POLICY, 0.95),
        # If has declarations only -> policy (medium confidence)
        ([PageType.DECLARATIONS], DocumentType.POLICY, 0.85),
        # If majority SOV -> SOV document
        ([PageType.SOV], DocumentType.SOV, 0.90),
        # If majority loss run -> loss run document
        ([PageType.LOSS_RUN], DocumentType.LOSS_RUN, 0.90),
        # If majority endorsement -> endorsement document
        ([PageType.ENDORSEMENT], DocumentType.ENDORSEMENT, 0.85),
        # If majority invoice -> invoice document
        ([PageType.INVOICE], DocumentType.INVOICE, 0.90),
    ]
    
    # Minimum pages for a section to be considered valid
    MIN_SECTION_PAGES = 1
    
    # Page types that should not form their own sections (merge with adjacent)
    MERGE_WITH_ADJACENT: List[PageType] = [
        PageType.UNKNOWN,
        PageType.BOILERPLATE,
        PageType.DUPLICATE,
    ]
    
    def __init__(self):
        """Initialize document profile builder."""
        LOGGER.info("Initialized DocumentProfileBuilder")
    
    @classmethod
    def get_instance(cls) -> "DocumentProfileBuilder":
        """Get or create singleton instance.
        
        Returns:
            Singleton instance of DocumentProfileBuilder
        """
        global _document_profile_builder_instance
        if _document_profile_builder_instance is None:
            _document_profile_builder_instance = cls()
        return _document_profile_builder_instance
    
    def build_profile(
        self,
        document_id: UUID,
        classifications: List[PageClassification],
    ) -> DocumentProfile:
        """Build document profile from page classifications.
        
        Args:
            document_id: Document UUID
            classifications: List of page classifications (sorted by page number)
            
        Returns:
            DocumentProfile with document type, section boundaries, and page map
        """
        if not classifications:
            LOGGER.warning(f"No classifications provided for document {document_id}")
            return DocumentProfile(
                document_id=document_id,
                document_type=DocumentType.UNKNOWN,
                confidence=0.0,
                section_boundaries=[],
                page_section_map={},
                page_type_distribution={},
            )
        
        # Sort classifications by page number
        sorted_classifications = sorted(classifications, key=lambda c: c.page_number)
        
        # Step 1: Calculate page type distribution
        page_type_distribution = self._calculate_distribution(sorted_classifications)
        
        # Step 2: Determine document type
        document_type, doc_confidence = self._infer_document_type(
            sorted_classifications, 
            page_type_distribution
        )
        
        # Step 3: Detect section boundaries
        section_boundaries = self._detect_section_boundaries(sorted_classifications)
        
        # Step 4: Build page-to-section map
        page_section_map = self._build_page_section_map(sorted_classifications)
        
        # Step 5: Calculate normalized section distribution and product concepts
        section_type_distribution, product_concepts = self._calculate_section_metrics(
            sorted_classifications
        )
        
        # Step 6: Determine document subtype
        document_subtype = self._infer_document_subtype(
            document_type, 
            page_type_distribution
        )
        
        # Step 7: Build metadata
        metadata = self._build_metadata(
            sorted_classifications, 
            section_boundaries,
            product_concepts
        )
        
        profile = DocumentProfile(
            document_id=document_id,
            document_type=document_type,
            document_subtype=document_subtype,
            confidence=doc_confidence,
            section_boundaries=section_boundaries,
            page_section_map=page_section_map,
            page_type_distribution=page_type_distribution,
            section_type_distribution=section_type_distribution,
            product_concepts=product_concepts,
            metadata=metadata,
        )
        
        LOGGER.info(
            f"Built document profile for {document_id}",
            extra={
                "document_type": document_type.value,
                "confidence": doc_confidence,
                "section_count": len(section_boundaries),
                "total_pages": len(classifications),
            }
        )
        
        return profile
    
    def _calculate_distribution(
        self, 
        classifications: List[PageClassification]
    ) -> Dict[str, int]:
        """Calculate raw page type distribution.
        
        Args:
            classifications: List of page classifications
            
        Returns:
            Dict mapping page type strings to counts
        """
        counter = Counter(c.page_type.value for c in classifications)
        return dict(counter)

    def _calculate_section_metrics(
        self,
        classifications: List[PageClassification]
    ) -> Tuple[Dict[str, int], List[str]]:
        """Calculate normalized section distribution and product concepts.
        
        Args:
            classifications: List of page classifications
            
        Returns:
            Tuple of (section_type_distribution, product_concepts)
        """
        all_section_types = []
        for c in classifications:
            if c.sections:
                for s in c.sections:
                    all_section_types.append(
                        SectionTypeMapper.page_type_to_section_type(s.section_type)
                    )
            else:
                all_section_types.append(
                    SectionTypeMapper.page_type_to_section_type(c.page_type)
                )
        
        # Filter out unknown/boilerplate for distribution
        significant_types = [
            st for st in all_section_types 
            if st.value not in ["unknown", "boilerplate", "duplicate"]
        ]
        
        # Section distribution (normalized SectionType names)
        counter = Counter(st.value for st in significant_types)
        section_type_distribution = dict(counter)
        
        # Product concepts (core categories)
        product_concepts = SectionTypeMapper.get_product_concepts(significant_types)
        
        return section_type_distribution, product_concepts
    
    def _infer_document_type(
        self,
        classifications: List[PageClassification],
        distribution: Dict[str, int],
    ) -> Tuple[DocumentType, float]:
        """Infer document type from page classifications.
        
        Uses rule-based inference to determine the most likely document type
        based on the presence and distribution of page types.
        
        Args:
            classifications: List of page classifications
            distribution: Page type distribution
            
        Returns:
            Tuple of (DocumentType, confidence score)
        """
        # Convert distribution keys to PageType for easier lookup
        page_types_present = set()
        for page_type_str in distribution.keys():
            try:
                page_types_present.add(PageType(page_type_str))
            except ValueError:
                continue
        
        # Apply inference rules in order
        for required_types, doc_type, base_confidence in self.DOCUMENT_TYPE_RULES:
            if all(pt in page_types_present for pt in required_types):
                # Calculate confidence based on coverage
                total_pages = len(classifications)
                matching_pages = sum(
                    distribution.get(pt.value, 0) 
                    for pt in required_types
                )
                coverage_ratio = matching_pages / total_pages if total_pages > 0 else 0
                
                # Adjust confidence based on coverage
                confidence = base_confidence * (0.5 + 0.5 * coverage_ratio)
                
                LOGGER.debug(
                    f"Document type inferred: {doc_type.value}",
                    extra={
                        "required_types": [pt.value for pt in required_types],
                        "coverage_ratio": coverage_ratio,
                        "confidence": confidence,
                    }
                )
                
                return doc_type, round(confidence, 3)
        
        # Fallback: use most common non-trivial page type
        non_trivial_types = {
            pt: count for pt, count in distribution.items()
            if pt not in [PageType.UNKNOWN.value, PageType.BOILERPLATE.value, PageType.DUPLICATE.value]
        }
        
        if non_trivial_types:
            most_common = max(non_trivial_types.items(), key=lambda x: x[1])
            try:
                dominant_page_type = PageType(most_common[0])
                doc_type = self.PAGE_TO_DOCUMENT_TYPE.get(
                    dominant_page_type, 
                    DocumentType.UNKNOWN
                )
                # Lower confidence for fallback inference
                confidence = 0.6 * (most_common[1] / len(classifications))
                return doc_type, round(confidence, 3)
            except ValueError:
                pass
        
        return DocumentType.UNKNOWN, 0.0
    
    def _detect_section_boundaries(
        self,
        classifications: List[PageClassification],
    ) -> List[SectionBoundary]:
        """Detect section boundaries from consecutive page type runs.
        
        Groups consecutive pages of the same type into sections.
        Merges trivial page types (unknown, boilerplate) with adjacent sections.
        
        Args:
            classifications: List of page classifications (sorted by page number)
            
        Returns:
            List of SectionBoundary objects
        """
        if not classifications:
            return []
        
        # Step 1: Create initial runs of consecutive same-type pages
        runs: List[Dict] = []
        current_run = {
            "page_type": classifications[0].page_type,
            "start_page": classifications[0].page_number,
            "end_page": classifications[0].page_number,
            "confidences": [classifications[0].confidence],
            "reasoning": classifications[0].reasoning,
        }
        
        for classification in classifications[1:]:
            if classification.page_type == current_run["page_type"]:
                # Extend current run
                current_run["end_page"] = classification.page_number
                current_run["confidences"].append(classification.confidence)
            else:
                # Save current run and start new one
                runs.append(current_run)
                current_run = {
                    "page_type": classification.page_type,
                    "start_page": classification.page_number,
                    "end_page": classification.page_number,
                    "confidences": [classification.confidence],
                    "reasoning": classification.reasoning,
                }
        
        # Don't forget the last run
        runs.append(current_run)
        
        # Step 2: Extract explicit section spans from multi-section pages
        span_boundaries = self._extract_span_boundaries(classifications)
        
        # Step 3: Merge trivial runs with adjacent sections
        merged_runs = self._merge_trivial_runs(runs)
        
        # Step 4: Convert runs to SectionBoundary objects and merge with spans
        boundaries = []
        for run in merged_runs:
            # Skip sections that are purely trivial types
            if run["page_type"] in self.MERGE_WITH_ADJACENT:
                continue
            
            # Check if this page run is already covered by explicit spans
            is_covered = False
            for span_b in span_boundaries:
                if span_b.start_page >= run["start_page"] and span_b.end_page <= run["end_page"]:
                    if span_b.section_type == run["page_type"]:
                        is_covered = True
                        break
            
            if is_covered:
                continue

            page_count = run["end_page"] - run["start_page"] + 1
            avg_confidence = sum(run["confidences"]) / len(run["confidences"])
            
            boundary = SectionBoundary(
                section_type=run["page_type"],
                start_page=run["start_page"],
                end_page=run["end_page"],
                confidence=round(avg_confidence, 3),
                page_count=page_count,
                anchor_text=run.get("reasoning"),
            )
            boundaries.append(boundary)
        
        # Combine and sort all boundaries
        all_boundaries = sorted(
            boundaries + span_boundaries, 
            key=lambda x: (x.start_page, x.start_line or 0)
        )
        
        LOGGER.debug(
            f"Detected {len(all_boundaries)} total section boundaries (including {len(span_boundaries)} spans)",
            extra={
                "sections": [
                    {"type": b.section_type.value, "pages": f"{b.start_page}-{b.end_page}"}
                    for b in all_boundaries
                ]
            }
        )
        
        return all_boundaries

    def _extract_span_boundaries(self, classifications: List[PageClassification]) -> List[SectionBoundary]:
        """Extract explicit section spans from pages."""
        span_boundaries = []
        for c in classifications:
            if c.sections:
                for s in c.sections:
                    span_boundaries.append(SectionBoundary(
                        section_type=s.section_type,
                        start_page=c.page_number,
                        end_page=c.page_number,
                        start_line=s.span.start_line if s.span else None,
                        end_line=s.span.end_line if s.span else None,
                        confidence=s.confidence,
                        page_count=1,
                        anchor_text=s.reasoning
                    ))
        return span_boundaries
    
    def _merge_trivial_runs(self, runs: List[Dict]) -> List[Dict]:
        """Merge trivial page type runs with adjacent sections.
        
        Trivial types (unknown, boilerplate, duplicate) are merged into
        the preceding section to create more coherent boundaries.
        
        Args:
            runs: List of run dictionaries
            
        Returns:
            List of merged run dictionaries
        """
        if len(runs) <= 1:
            return runs
        
        merged = []
        for run in runs:
            if run["page_type"] in self.MERGE_WITH_ADJACENT:
                # Try to merge with previous run
                if merged:
                    prev_run = merged[-1]
                    prev_run["end_page"] = run["end_page"]
                    prev_run["confidences"].extend(run["confidences"])
                else:
                    # No previous run, keep as-is (will be skipped later)
                    merged.append(run)
            else:
                merged.append(run)
        
        return merged
    
    def _build_page_section_map(
        self,
        classifications: List[PageClassification],
    ) -> Dict[int, str]:
        """Build mapping of page numbers to canonical section types.
        
        For multi-section pages, we join section names with a comma.
        """
        page_section_map = {}
        
        for classification in classifications:
            # If multiple sections detected, combine them
            if classification.sections:
                section_types = []
                for s in classification.sections:
                    st = SectionTypeMapper.page_type_to_section_type(s.section_type)
                    if st.value not in section_types:
                        section_types.append(st.value)
                page_section_map[classification.page_number] = ",".join(section_types)
            else:
                # Convert PageType to canonical SectionType using mapper
                section_type = SectionTypeMapper.page_type_to_section_type(classification.page_type)
                page_section_map[classification.page_number] = section_type.value
            
            if not classification.sections and classification.page_type.value != page_section_map[classification.page_number]:
                LOGGER.debug(
                    f"Normalized page {classification.page_number} section type: "
                    f"'{classification.page_type.value}' -> '{page_section_map[classification.page_number]}'"
                )
        
        return page_section_map
    
    def _infer_document_subtype(
        self,
        document_type: DocumentType,
        distribution: Dict[str, int],
    ) -> Optional[str]:
        """Infer document subtype from page distribution.
        
        Args:
            document_type: Inferred document type
            distribution: Page type distribution
            
        Returns:
            Optional subtype string
        """
        if document_type != DocumentType.POLICY:
            return None
        
        # Infer policy subtype based on section presence
        has_sov = distribution.get(PageType.SOV.value, 0) > 0
        has_loss_run = distribution.get(PageType.LOSS_RUN.value, 0) > 0
        
        # Check for coverage types in reasoning (would need more sophisticated analysis)
        # For now, use simple heuristics
        if has_sov:
            return "commercial_property"
        elif has_loss_run:
            return "claims_made"
        
        return "general"
    
    def _build_metadata(
        self,
        classifications: List[PageClassification],
        boundaries: List[SectionBoundary],
        product_concepts: List[str] = None
    ) -> Dict:
        """Build metadata dictionary for the profile.
        
        Args:
            classifications: List of page classifications
            boundaries: List of section boundaries
            product_concepts: List of core product concepts found
            
        Returns:
            Metadata dictionary
        """
        # Count pages by processing status
        pages_to_process = sum(1 for c in classifications if c.should_process)
        pages_skipped = sum(1 for c in classifications if not c.should_process)
        duplicates = sum(1 for c in classifications if c.page_type == PageType.DUPLICATE)
        
        # Calculate average confidence
        avg_confidence = (
            sum(c.confidence for c in classifications) / len(classifications)
            if classifications else 0.0
        )
        
        # Use product concepts for accurate flags if available
        if product_concepts:
            has_declarations = "declarations" in product_concepts
            has_coverages = "coverages" in product_concepts
            has_endorsements = "endorsements" in product_concepts
        else:
            # Fallback to strict enum matching
            has_declarations = any(
                b.section_type == PageType.DECLARATIONS for b in boundaries
            )
            has_coverages = any(
                b.section_type == PageType.COVERAGES for b in boundaries
            )
            has_endorsements = any(
                b.section_type == PageType.ENDORSEMENT for b in boundaries
            )
        
        return {
            "total_pages": len(classifications),
            "pages_to_process": pages_to_process,
            "pages_skipped": pages_skipped,
            "duplicates_detected": duplicates,
            "section_count": len(boundaries),
            "average_confidence": round(avg_confidence, 3),
            "has_declarations": has_declarations,
            "has_coverages": has_coverages,
            "has_endorsements": has_endorsements,
            "product_concepts": product_concepts or [],
        }



