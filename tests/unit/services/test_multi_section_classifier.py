import pytest
from app.models.page_analysis_models import PageSignals, PageType
from app.services.processed.services.analysis.page_classifier import PageClassifier

def test_detect_section_spans_oriental_motor_policy():
    """Test detection on the specific Oriental Insurance motor policy content."""
    classifier = PageClassifier()
    
    # Content from the user's log
    lines = [
        "## The Oriental Insurance Company Limited",
        "## MOTOR INSURANCE CERTIFICATE CUM POLICY SCHEDULE PRIVATE CAR PACKAGE POLICY - ZONE B",
        "OUR ORIENTAL - MY TVS EMERGENCY ROADSIDE ASSISTANCE SCHEME",
        "Membership No. 5580/243600",
        "Policy No. 243600/3426",
        "",
        "## Agent/Broker Details",
        "Dev.Off.Code: ND0000000141 DIRECT DO 4 JAIPUR",
        "Period of Insurance : FROM 00:00 ON 22/12/2016 TO MIDNIGHT OF 21/12/2017",
        "",
        "## Particulars of Insured Vehicle:",
        "| Registration Mark & Place | Engine No. & Chassis No. | Type Of Body Make - Model |",
        "| RJ 23 CA 4351 Sikar | M30227 M30227 | FORD-FORD FIGO 1.4 HATCHBACK DURATORO LXI |",
        "",
        "## Limitations as to use:",
        "- 1 The Policy covers use of the vehicle for any purpose other than...",
        "",
        "## Driver:",
        "Any person including the insured...",
        "",
        "## Limit of Liability:",
        "Under Section II-I(1) in respect of any one accident: as per Motor Vehicles Act, 1988.",
        "",
        "## Insured's Declared Value",
        "| For the Vehicle | For Trailers | Total Value |",
        "| 2,30,769 | | 2,30,769 |",
    ]
    
    signals = PageSignals(
        page_number=1,
        top_lines=lines[:5],
        all_lines=lines,
        text_density=0.8,
        has_tables=True,
        max_font_size=20.0,
        page_hash="oriental_p1"
    )
    
    classification = classifier.classify(signals)
    
    # Should classify as declarations initially
    assert classification.page_type == PageType.DECLARATIONS
    
    # Should have multiple sections
    section_types = [s.section_type for s in classification.sections]
    
    # 1. Declarations (starts at line 1)
    assert PageType.DECLARATIONS in section_types
    # 2. Vehicle Details (starts at line 11)
    assert PageType.VEHICLE_DETAILS in section_types
    # 3. Liability Coverages (starts at line 21)
    assert PageType.LIABILITY_COVERAGES in section_types
    # 4. Insured Declared Value (starts at line 24)
    assert PageType.INSURED_DECLARED_VALUE in section_types
    
    # Check specific boundaries
    vehicle_span = next(s for s in classification.sections if s.section_type == PageType.VEHICLE_DETAILS)
    assert vehicle_span.span.start_line == 11
    
    liability_span = next(s for s in classification.sections if s.section_type == PageType.LIABILITY_COVERAGES)
    assert liability_span.span.start_line == 21
    
    idv_span = next(s for s in classification.sections if s.section_type == PageType.INSURED_DECLARED_VALUE)
    assert idv_span.span.start_line == 24
    
    # Verify should_process is True
    assert classification.should_process is True

def test_detect_section_spans_single_section():
    """Test that a single section page still works correctly."""
    classifier = PageClassifier()
    
    lines = [
        "GENERAL CONDITIONS",
        "1. Cancellation",
        "This policy may be cancelled by the insured...",
        "2. Other Insurance",
        "If there is other insurance covering the same loss...",
    ]
    
    signals = PageSignals(
        page_number=10,
        top_lines=lines[:5],
        all_lines=lines,
        text_density=0.9,
        has_tables=False,
        max_font_size=16.0,
        page_hash="def"
    )
    
    classification = classifier.classify(signals)
    
    assert classification.page_type == PageType.CONDITIONS
    # Even single sections might be detected as a span now
    if classification.sections:
        assert len(classification.sections) == 1
        assert classification.sections[0].section_type == PageType.CONDITIONS

from uuid import uuid4
from app.services.processed.services.analysis.document_profile_builder import DocumentProfileBuilder

def test_document_profile_product_concepts():
    """Test that document profile correctly derives product concepts and metadata."""
    classifier = PageClassifier()
    builder = DocumentProfileBuilder.get_instance()
    doc_id = uuid4()
    
    # Page 1: Multi-section (Declarations + Vehicle + Liability)
    lines_p1 = [
        "## Policy Schedule",
        "Policy No. 12345",
        "## Particulars of Vehicle",
        "Engine No. E123",
        "## Limit of Liability",
        "Liability Limit: 1,000,000"
    ]
    signals_p1 = PageSignals(
        page_number=1,
        top_lines=lines_p1[:2],
        all_lines=lines_p1,
        text_density=0.8,
        has_tables=True,
        max_font_size=20.0,
        page_hash="p1"
    )
    
    # Page 2: Coverages
    lines_p2 = [
        "## Insuring Agreement",
        "The Company will indemnify the insured..."
    ]
    signals_p2 = PageSignals(
        page_number=2,
        top_lines=lines_p2[:1],
        all_lines=lines_p2,
        text_density=0.9,
        has_tables=False,
        max_font_size=16.0,
        page_hash="p2"
    )
    
    classifications = [
        classifier.classify(signals_p1),
        classifier.classify(signals_p2)
    ]
    
    profile = builder.build_profile(doc_id, classifications)
    
    # Verify product concepts
    assert "declarations" in profile.product_concepts
    assert "coverages" in profile.product_concepts
    
    # Verify metadata flags (THE CORE FIX)
    assert profile.has_declarations is True
    assert profile.has_coverages is True
    
    # Verify section distribution (normalized)
    assert profile.section_type_distribution["declarations"] == 1
    assert profile.section_type_distribution["vehicle_details"] == 1
    assert profile.section_type_distribution["liability_coverages"] == 1
    assert profile.section_type_distribution["coverages"] == 1
