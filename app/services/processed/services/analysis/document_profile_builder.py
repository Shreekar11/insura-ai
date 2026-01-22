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
import re

from app.models.page_analysis_models import (
    PageClassification,
    PageType,
    SemanticSection,
    DocumentType,
    DocumentProfile,
    SectionBoundary,
    SemanticRole,
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
        PageType.COVERAGES_CONTEXT: DocumentType.POLICY,
        PageType.COVERAGE_GRANT: DocumentType.POLICY,
        PageType.COVERAGE_EXTENSION: DocumentType.POLICY,
        PageType.LIMITS: DocumentType.POLICY,
        PageType.INSURED_DEFINITION: DocumentType.POLICY,
        PageType.TABLE_OF_CONTENTS: DocumentType.POLICY,
        PageType.ACORD_APPLICATION: DocumentType.ACORD_APPLICATION,
        PageType.PROPOSAL: DocumentType.PROPOSAL,
        PageType.CERTIFICATE_OF_INSURANCE: DocumentType.CERTIFICATE,
        PageType.BOILERPLATE: DocumentType.UNKNOWN,
        PageType.DUPLICATE: DocumentType.UNKNOWN,
        PageType.UNKNOWN: DocumentType.UNKNOWN,
    }
    
    DOCUMENT_TYPE_RULES: List[Tuple[List[PageType], DocumentType, float]] = [
        # If has declarations AND coverages AND endorsements -> policy bundle (very high confidence)
        ([PageType.DECLARATIONS, PageType.COVERAGES, PageType.ENDORSEMENT], DocumentType.POLICY_BUNDLE, 0.95),
        # If has declarations AND endorsements -> policy bundle (high confidence)
        ([PageType.DECLARATIONS, PageType.ENDORSEMENT], DocumentType.POLICY_BUNDLE, 0.90),
        # If has certificate AND endorsements -> policy bundle (high confidence)
        ([PageType.CERTIFICATE_OF_INSURANCE, PageType.ENDORSEMENT], DocumentType.POLICY_BUNDLE, 0.90),
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
        # If majority ACORD -> ACORD document
        ([PageType.ACORD_APPLICATION], DocumentType.ACORD_APPLICATION, 0.95),
        # If majority Proposal -> Proposal document
        ([PageType.PROPOSAL], DocumentType.PROPOSAL, 0.90),
        # If majority Certificate -> Certificate document
        ([PageType.CERTIFICATE_OF_INSURANCE], DocumentType.CERTIFICATE, 0.95),
        # If has canonical policy sections (Base Policy Rule)
        ([PageType.COVERAGES, PageType.EXCLUSIONS, PageType.CONDITIONS], DocumentType.POLICY, 0.90),
        # If has granular coverage sections
        ([PageType.COVERAGE_GRANT, PageType.LIMITS], DocumentType.POLICY, 0.95),
        # If has coverage context (ISO Symbol Tables)
        ([PageType.COVERAGES_CONTEXT], DocumentType.POLICY, 0.85),
    ]
    
    # Minimum pages for a section to be considered valid
    MIN_SECTION_PAGES = 1
    
    MERGE_WITH_ADJACENT: List[PageType] = [
        PageType.UNKNOWN,
        PageType.BOILERPLATE,
        PageType.DUPLICATE,
        PageType.TABLE_OF_CONTENTS,
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
        workflow_name: Optional[str] = None,
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
        
        # Pass 1: Calculation & Document Type Inference
        page_type_distribution = self._calculate_distribution(sorted_classifications)
        document_type, doc_confidence = self._infer_document_type(
            sorted_classifications, 
            page_type_distribution,
            workflow_name=workflow_name
        )
        
        # Pass 2: Detect section boundaries (Semantic & Context Aware)
        section_boundaries = self._detect_section_boundaries(
            sorted_classifications, 
            doc_type=document_type
        )
        
        # Pass 3: Build page-to-section map (Semantic with inheritance)
        page_section_map = self._build_page_section_map(
            sorted_classifications,
            doc_type=document_type
        )
        
        # Pass 4: Calculate metrics & product concepts
        section_type_distribution, product_concepts = self._calculate_section_metrics(
            sorted_classifications
        )
        
        # Determine document subtype
        document_subtype = self._infer_document_subtype(
            document_type, 
            page_type_distribution
        )
        
        # Build metadata
        metadata = self._build_metadata(
            sorted_classifications, 
            section_boundaries,
            product_concepts
        )

        if document_type == DocumentType.POLICY and metadata.get("has_endorsements"):
            document_type = DocumentType.POLICY_BUNDLE
        
        # Determine semantic capabilities
        capabilities = []
        if document_type == DocumentType.POLICY_BUNDLE or metadata.get("has_endorsements"):
            capabilities.append("endorsement_semantic_projection")
        
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
            semantic_capabilities=capabilities
        )
        
        LOGGER.info(
            f"Built document profile for {document_id}",
            extra={
                "document_type": document_type.value,
                "confidence": doc_confidence,
                "section_count": len(section_boundaries),
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
        """Calculate normalized section distribution and product concepts."""
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
        
        significant_types = [
            st for st in all_section_types 
            if st.value not in ["unknown", "boilerplate", "duplicate"]
        ]
        
        counter = Counter(st.value for st in significant_types)
        product_concepts = SectionTypeMapper.get_product_concepts(significant_types)
        
        return dict(counter), product_concepts
    
    def _infer_document_type(
        self,
        classifications: List[PageClassification],
        distribution: Dict[str, int],
        workflow_name: Optional[str] = None,
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
        inferred_type = DocumentType.UNKNOWN
        final_confidence = 0.0
        
        # Determine document type (internal helper for override)
        inferred_type = DocumentType.UNKNOWN
        final_confidence = 0.0

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
                inferred_type = doc_type
                final_confidence = round(confidence, 3)
                break
        
        if inferred_type == DocumentType.UNKNOWN:
            # Fallback: use most common non-trivial page type
            non_trivial_types = {
                pt: count for pt, count in distribution.items()
                if pt not in [PageType.UNKNOWN.value, PageType.BOILERPLATE.value, PageType.DUPLICATE.value]
            }
            
            if non_trivial_types:
                most_common = max(non_trivial_types.items(), key=lambda x: x[1])
                try:
                    dominant_page_type = PageType(most_common[0])
                    inferred_type = self.PAGE_TO_DOCUMENT_TYPE.get(
                        dominant_page_type, 
                        DocumentType.UNKNOWN
                    )
                    # Lower confidence for fallback inference
                    final_confidence = round(0.6 * (most_common[1] / len(classifications)), 3)
                except ValueError:
                    pass

        # Workflow-aware override: Quote vs Policy 
        # (Quote and Policy share same sections/fields, differ by context)
        if workflow_name == "quote_comparison":
            if inferred_type == DocumentType.POLICY:
                LOGGER.info("Overriding DocumentType.POLICY to DocumentType.QUOTE for quote_comparison workflow")
                inferred_type = DocumentType.QUOTE
        elif workflow_name != "quote_comparison":
            if inferred_type == DocumentType.QUOTE:
                LOGGER.info(f"Overriding DocumentType.QUOTE to DocumentType.POLICY for workflow: {workflow_name}")
                inferred_type = DocumentType.POLICY

        return inferred_type, final_confidence
    
    def _detect_section_boundaries(
        self,
        classifications: List[PageClassification],
        doc_type: DocumentType = DocumentType.UNKNOWN
    ) -> List[SectionBoundary]:
        """Detect section boundaries with improved semantic awareness."""
        if not classifications: return []
        
        # Step 1: Detect raw runs of same-type pages
        runs = []
        current = {
            "page_type": classifications[0].page_type,
            "start_page": classifications[0].page_number,
            "end_page": classifications[0].page_number,
            "confidences": [classifications[0].confidence],
            "reasoning": classifications[0].reasoning,
            "semantic_role": classifications[0].semantic_role,
            "coverage_effects": classifications[0].coverage_effects or [],
            "exclusion_effects": classifications[0].exclusion_effects or [],
        }
        
        for c in classifications[1:]:
            if c.page_type == current["page_type"]:
                current["end_page"] = c.page_number
                current["confidences"].append(c.confidence)
                # Inherit semantic info if current run lacks it but this page has it
                if not current.get("semantic_role") or current.get("semantic_role") == SemanticRole.UNKNOWN:
                    if c.semantic_role and c.semantic_role != SemanticRole.UNKNOWN:
                        current["semantic_role"] = c.semantic_role
                        current["coverage_effects"] = c.coverage_effects or []
                        current["exclusion_effects"] = c.exclusion_effects or []
            else:
                runs.append(current)
                current = {
                    "page_type": c.page_type,
                    "start_page": c.page_number,
                    "end_page": c.page_number,
                    "confidences": [c.confidence],
                    "reasoning": c.reasoning,
                    "semantic_role": c.semantic_role,
                    "coverage_effects": c.coverage_effects,
                    "exclusion_effects": c.exclusion_effects,
                }
        runs.append(current)
        
        # Step 2: Extract explicit span boundaries (Semantic First)
        span_boundaries = self._extract_span_boundaries(classifications, doc_type=doc_type)
        
        # Step 3: Merge trivial runs
        merged_runs = self._merge_trivial_runs(runs)
        
        # Step 4: Convert runs to boundaries
        boundaries = []
        for r in merged_runs:
            if r["page_type"] in self.MERGE_WITH_ADJACENT: continue
            
            # Skip if already covered by explicit spans
            if any(sb.start_page == r["start_page"] and sb.end_page == r["end_page"] for sb in span_boundaries):
                continue
                
            avg_conf = sum(r["confidences"]) / len(r["confidences"])
            semantic = SectionTypeMapper.page_to_semantic(r["page_type"])
            
            non_extractable = {
                SemanticSection.UNKNOWN, 
                SemanticSection.BOILERPLATE, 
                SemanticSection.CERTIFICATE,
                SemanticSection.CERTIFICATE_OF_INSURANCE,
                SemanticSection.TABLE_OF_CONTENTS
            }
            
            is_extractable = True
            if semantic in non_extractable:
                is_extractable = False
            
            # Context-aware extraction gating
            if semantic == SemanticSection.DECLARATIONS:
                if doc_type in {DocumentType.POLICY_BUNDLE, DocumentType.ENDORSEMENT}:
                    if r["start_page"] > 2:
                        is_extractable = False
            
            # Calculate effective section type
            semantic_role = r.get("semantic_role") if (doc_type != DocumentType.POLICY or r["page_type"] == PageType.ENDORSEMENT) else SemanticRole.UNKNOWN
            
            # HARD GUARD for Certificates - profile level
            if r["page_type"] == PageType.CERTIFICATE_OF_INSURANCE:
                semantic_role = SemanticRole.UNKNOWN
                
            effective_type = SectionTypeMapper.resolve_effective_section_type(
                r["page_type"], 
                semantic_role
            )

            boundaries.append(SectionBoundary(
                section_type=r["page_type"],
                semantic_section=semantic,
                start_page=r["start_page"],
                end_page=r["end_page"],
                confidence=round(avg_conf, 3),
                page_count=r["end_page"] - r["start_page"] + 1,
                anchor_text=r.get("reasoning"),
                extractable=is_extractable,
                semantic_role=semantic_role,
                effective_section_type=effective_type,
                coverage_effects=r.get("coverage_effects") or [] if (doc_type != DocumentType.POLICY or r["page_type"] == PageType.ENDORSEMENT) else [],
                exclusion_effects=r.get("exclusion_effects") or [] if (doc_type != DocumentType.POLICY or r["page_type"] == PageType.ENDORSEMENT) else []
            ))
            
        all_boundaries = sorted(boundaries + span_boundaries, key=lambda x: (x.start_page, x.start_line or 0))
        
        # Step 5: Apply structural inheritance for base policies
        if doc_type == DocumentType.POLICY:
            self._apply_structural_inheritance(all_boundaries)
            
        return all_boundaries

    def _apply_structural_inheritance(self, boundaries: List[SectionBoundary]):
        """Apply structural context inheritance for base policies.
        
        For example, sections following 'SECTION II - LIABILITY' should be tagged
        with liability context until 'SECTION III - PHYSICAL DAMAGE' is encountered.
        """
        current_context = None
        
        # Context triggers for ISO forms (ordered specifically to avoid partial matches)
        triggers = [
            (r"SECTION\s+V\b", "definitions"),
            (r"SECTION\s+IV\b", "conditions"),
            (r"SECTION\s+III\b", "physical_damage"),
            (r"SECTION\s+II\b", "liability"),
            (r"SECTION\s+I\b", "covered_autos"),
        ]
        
        for b in boundaries:
            anchor = (b.anchor_text or "").upper()
            
            # Check for context switch
            for pattern, context in triggers:
                if re.search(pattern, anchor, re.IGNORECASE):
                    current_context = context
                    break
            
            # Apply context to metadata
            if current_context:
                b.metadata["policy_section_context"] = current_context
                
                # If it's a generic coverage/exclusion, refine the semantic section
                if b.semantic_section == SemanticSection.COVERAGES:
                    if current_context == "liability":
                        b.semantic_section = SemanticSection.LIABILITY_COVERAGE
                    elif current_context == "physical_damage":
                        b.semantic_section = SemanticSection.PHYSICAL_DAMAGE_COVERAGE
                elif b.semantic_section == SemanticSection.EXCLUSIONS:
                    if current_context == "liability":
                        b.semantic_section = SemanticSection.LIABILITY_EXCLUSIONS
                    elif current_context == "physical_damage":
                        b.semantic_section = SemanticSection.PHYSICAL_DAMAGE_EXCLUSIONS

    def _extract_span_boundaries(
        self, 
        classifications: List[PageClassification],
        doc_type: DocumentType = DocumentType.UNKNOWN
    ) -> List[SectionBoundary]:
        """Extract explicit semantic section spans from pages."""
        span_boundaries = []
        for c in classifications:
            if c.sections:
                for s in c.sections:
                    semantic = SectionTypeMapper.page_to_semantic(s.section_type)
                    
                    # Normalize for boundary
                    core_st = SectionTypeMapper.page_type_to_section_type(s.section_type)
                    norm_pt = SectionTypeMapper.section_type_to_page_type(
                        SectionTypeMapper.normalize_to_core_section(core_st)
                    )

                    non_extractable = {
                        SemanticSection.UNKNOWN, 
                        SemanticSection.BOILERPLATE, 
                        SemanticSection.CERTIFICATE,
                        SemanticSection.CERTIFICATE_OF_INSURANCE,
                        SemanticSection.TABLE_OF_CONTENTS
                    }

                    is_extractable = True
                    if semantic in non_extractable:
                        is_extractable = False
                    
                    if semantic == SemanticSection.DECLARATIONS:
                        if doc_type in {DocumentType.POLICY_BUNDLE, DocumentType.ENDORSEMENT}:
                            if c.page_number > 2:
                                is_extractable = False
                    
                    # Calculate effective section type
                    semantic_role = s.semantic_role if (doc_type != DocumentType.POLICY or s.section_type == PageType.ENDORSEMENT) else SemanticRole.UNKNOWN
                    effective_type = SectionTypeMapper.resolve_effective_section_type(
                        norm_pt, 
                        semantic_role
                    )

                    span_boundaries.append(SectionBoundary(
                        section_type=norm_pt,
                        semantic_section=semantic,
                        start_page=c.page_number,
                        end_page=c.page_number,
                        start_line=s.span.start_line if s.span else None,
                        end_line=s.span.end_line if s.span else None,
                        confidence=s.confidence,
                        page_count=1,
                        anchor_text=s.reasoning or c.reasoning,
                        extractable=is_extractable,
                        semantic_role=semantic_role,
                        effective_section_type=effective_type,
                        coverage_effects=s.coverage_effects if (doc_type != DocumentType.POLICY or s.section_type == PageType.ENDORSEMENT) else [],
                        exclusion_effects=s.exclusion_effects if (doc_type != DocumentType.POLICY or s.section_type == PageType.ENDORSEMENT) else []
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
                    # Inherit semantic metadata if previous run lacks it but current has it
                    if not prev_run.get("semantic_role") or prev_run.get("semantic_role") == SemanticRole.UNKNOWN:
                         if run.get("semantic_role") and run.get("semantic_role") != SemanticRole.UNKNOWN:
                             prev_run["semantic_role"] = run["semantic_role"]
                             prev_run["coverage_effects"] = run.get("coverage_effects", [])
                             prev_run["exclusion_effects"] = run.get("exclusion_effects", [])
                else:
                    # No previous run, keep as-is (will be skipped later)
                    merged.append(run)
            else:
                merged.append(run)
        
        return merged
    
    def _build_page_section_map(
        self,
        classifications: List[PageClassification],
        doc_type: DocumentType = DocumentType.UNKNOWN
    ) -> Dict[int, str]:
        """Build mapping of page numbers to semantic section types.
        
        Enforces one semantic section per page, prioritizing insurance concepts.
        Implements semantic inheritance (forward fill) for unknown pages.
        """
        page_section_map = {}
        last_meaningful_semantic = SemanticSection.UNKNOWN
        
        for c in classifications:
            selected_semantic = SemanticSection.UNKNOWN
            if c.sections:
                priority = [
                    SemanticSection.ENDORSEMENT,
                    SemanticSection.COVERAGES,
                    SemanticSection.EXCLUSIONS,
                    SemanticSection.DECLARATIONS,
                    SemanticSection.CONDITIONS,
                    SemanticSection.DEFINITIONS,
                    SemanticSection.CERTIFICATE_OF_INSURANCE,
                    SemanticSection.CERTIFICATE,
                ]
                
                found_semantics = [SectionTypeMapper.page_to_semantic(s.section_type) for s in c.sections]
                
                for p_type in priority:
                    if p_type in found_semantics:
                        selected_semantic = p_type
                        break
                
                # Fallback if no priority match
                if selected_semantic == SemanticSection.UNKNOWN and found_semantics:
                    meaningful = [s for s in found_semantics if s != SemanticSection.UNKNOWN]
                    if meaningful:
                        selected_semantic = meaningful[0]
            else:
                selected_semantic = SectionTypeMapper.page_to_semantic(c.page_type)

            # Pass 3: Semantic Inheritance
            if selected_semantic == SemanticSection.UNKNOWN or selected_semantic == SemanticSection.BOILERPLATE:
                # Inherit from last semantic if current is unknown/boilerplate
                if c.page_type in self.MERGE_WITH_ADJACENT or c.page_type == PageType.UNKNOWN:
                    # Inheritance only makes sense if we were in an active section
                    if last_meaningful_semantic not in {SemanticSection.UNKNOWN, SemanticSection.BOILERPLATE}:
                        # mid-policy continuity: if we are between significant sections and 
                        # text contains related keywords, inherit
                        coverage_keywords = [r"pay", r"limit", r"loss", r"liability"]
                        exclusion_keywords = [r"not\s+apply", r"exclude", r"except"]
                        
                        if last_meaningful_semantic in {SemanticSection.COVERAGES, SemanticSection.LIABILITY_COVERAGE}:
                             if any(re.search(kw, c.reasoning, re.IGNORECASE) for kw in coverage_keywords):
                                 selected_semantic = last_meaningful_semantic
                             else:
                                 selected_semantic = last_meaningful_semantic # Fallback for mid-policy consistency
                        elif last_meaningful_semantic == SemanticSection.EXCLUSIONS:
                             if any(re.search(kw, c.reasoning, re.IGNORECASE) for kw in exclusion_keywords):
                                 selected_semantic = last_meaningful_semantic
                             else:
                                 selected_semantic = last_meaningful_semantic # Fallback for mid-policy consistency
                        else:
                            selected_semantic = last_meaningful_semantic
            
            # Pass 4: Special case forward-fill for DEFINITIONS (Forward Fill logic)
            # If current page has high density of definitions (means:) it should inherit DEFINITIONS
            # This is partly handled by PageClassifier, but we enforce it here for continuity
            if selected_semantic == SemanticSection.COVERAGES and last_meaningful_semantic == SemanticSection.DEFINITIONS:
                # If we're in the middle of a definitions run, avoid flipping back to coverages too easily
                selected_semantic = SemanticSection.DEFINITIONS

            page_section_map[c.page_number] = selected_semantic.value
            
            # Update last meaningful semantic for inheritance
            inheritance_sources = {
                SemanticSection.ENDORSEMENT,
                SemanticSection.COVERAGES,
                SemanticSection.EXCLUSIONS,
                SemanticSection.CONDITIONS,
                SemanticSection.DEFINITIONS,
                SemanticSection.LIABILITY_COVERAGE,
                SemanticSection.PHYSICAL_DAMAGE_COVERAGE
            }
            if selected_semantic in inheritance_sources:
                last_meaningful_semantic = selected_semantic
            elif selected_semantic == SemanticSection.CERTIFICATE_OF_INSURANCE:
                # Break inheritance on certificates
                last_meaningful_semantic = SemanticSection.UNKNOWN
            elif selected_semantic not in {SemanticSection.UNKNOWN, SemanticSection.BOILERPLATE}:
                last_meaningful_semantic = SemanticSection.UNKNOWN
                
        return page_section_map
    
    def _infer_document_subtype(
        self,
        document_type: DocumentType,
        distribution: Dict[str, int],
    ) -> Optional[str]:
        """Infer document subtype from page distribution."""
        if document_type not in [DocumentType.POLICY, DocumentType.POLICY_BUNDLE]:
            return None
        
        if distribution.get(PageType.SOV.value, 0) > 0:
            return "commercial_property"
        elif distribution.get(PageType.LOSS_RUN.value, 0) > 0:
            return "claims_made"
        elif distribution.get(PageType.VEHICLE_DETAILS.value, 0) > 0:
            return "commercial_auto"
        
        return "general"
    
    def _build_metadata(
        self,
        classifications: List[PageClassification],
        boundaries: List[SectionBoundary],
        product_concepts: List[str] = None
    ) -> Dict:
        """Build metadata dictionary with semantic awareness."""
        pages_to_process = sum(1 for c in classifications if c.should_process)
        
        has_declarations = "declarations" in (product_concepts or [])
        has_endorsements = any(b.semantic_section == SemanticSection.ENDORSEMENT for b in boundaries)
        
        return {
            "total_pages": len(classifications),
            "pages_to_process": pages_to_process,
            "section_count": len(boundaries),
            "has_declarations": has_declarations,
            "has_endorsements": has_endorsements,
            "product_concepts": product_concepts or [],
        }



