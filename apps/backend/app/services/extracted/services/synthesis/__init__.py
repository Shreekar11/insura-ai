"""Synthesis services for transforming endorsement data into effective coverage/exclusion output.

This module provides the two-document extraction pipeline for insurance policy processing:

1. DocumentTypeClassifier - Identifies base forms vs endorsements
2. BaseFormExtractor - Extracts standard provisions from ISO base forms
3. CoverageSynthesizer - Synthesizes coverage modifications from endorsements
4. ExclusionSynthesizer - Synthesizes exclusion modifications from endorsements
5. DescriptionGenerator - Creates human-readable descriptions
6. SynthesisOrchestrator - Coordinates the full synthesis pipeline

The pipeline handles:
- Base policy forms (CA 00 01, CG 00 01, etc.) with standard provisions
- Endorsement packages that modify base policy terms
- Merging base form provisions with endorsement modifications
- Generating FurtherAI-compatible output format
"""

from app.services.extracted.services.synthesis.coverage_synthesizer import CoverageSynthesizer
from app.services.extracted.services.synthesis.exclusion_synthesizer import ExclusionSynthesizer
from app.services.extracted.services.synthesis.base_coverage_inference import BaseCoverageInferenceService
from app.services.extracted.services.synthesis.synthesis_orchestrator import SynthesisOrchestrator
from app.services.extracted.services.synthesis.description_generator import (
    DescriptionGenerator,
    create_description_generator,
)

__all__ = [
    # Core synthesizers
    "CoverageSynthesizer",
    "ExclusionSynthesizer",
    "BaseCoverageInferenceService",
    "SynthesisOrchestrator",
    # Description generation
    "DescriptionGenerator",
    "create_description_generator",
]
