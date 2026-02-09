"""Standard coverage and exclusion taxonomy for canonical ID generation.

This module provides:
1. Standard ISO coverage codes mapped to coverage names
2. Canonical ID generation functions
3. Coverage name normalization and matching utilities

The taxonomy enables consistent entity matching across documents
by mapping various coverage name variations to standard identifiers.
"""

import re
from typing import Optional, Dict, List, Tuple
from enum import Enum


class CoverageCategory(str, Enum):
    """High-level coverage categories."""
    AUTO = "auto"
    GENERAL_LIABILITY = "gl"
    PROPERTY = "property"
    WORKERS_COMP = "wc"
    UMBRELLA = "umbrella"
    PROFESSIONAL = "professional"
    CYBER = "cyber"
    INLAND_MARINE = "im"
    UNKNOWN = "unknown"


# Standard coverage identifiers mapped to common name variations
# Format: canonical_id -> (standard_name, [name_variations], category, iso_form)
COVERAGE_TAXONOMY: Dict[str, Tuple[str, List[str], CoverageCategory, Optional[str]]] = {
    # ============= AUTO COVERAGES (CA 00 01) =============
    "CA_LIABILITY": (
        "Covered Autos Liability Coverage",
        [
            "covered autos liability",
            "auto liability",
            "business auto liability",
            "commercial auto liability",
            "automobile liability",
            "vehicle liability",
            "liability coverage - auto",
        ],
        CoverageCategory.AUTO,
        "CA 00 01",
    ),
    "CA_COMPREHENSIVE": (
        "Comprehensive Coverage",
        [
            "comprehensive",
            "comprehensive coverage",
            "other than collision",
            "otc coverage",
        ],
        CoverageCategory.AUTO,
        "CA 00 01",
    ),
    "CA_COLLISION": (
        "Collision Coverage",
        [
            "collision",
            "collision coverage",
            "collision loss",
        ],
        CoverageCategory.AUTO,
        "CA 00 01",
    ),
    "CA_SPECIFIED_PERILS": (
        "Specified Causes Of Loss Coverage",
        [
            "specified causes of loss",
            "specified perils",
            "named perils auto",
        ],
        CoverageCategory.AUTO,
        "CA 00 01",
    ),
    "CA_UNINSURED_MOTORIST": (
        "Uninsured Motorists Coverage",
        [
            "uninsured motorist",
            "uninsured motorists",
            "um coverage",
            "uim coverage",
            "underinsured motorist",
        ],
        CoverageCategory.AUTO,
        "CA 00 01",
    ),
    "CA_MEDICAL_PAYMENTS": (
        "Medical Payments Coverage",
        [
            "medical payments",
            "med pay",
            "medpay",
            "auto medical payments",
        ],
        CoverageCategory.AUTO,
        "CA 00 01",
    ),
    "CA_PIP": (
        "Personal Injury Protection",
        [
            "personal injury protection",
            "pip",
            "pip coverage",
            "no-fault",
        ],
        CoverageCategory.AUTO,
        "CA 00 01",
    ),
    "CA_HIRED_AUTO": (
        "Hired Auto Coverage",
        [
            "hired auto",
            "hired car",
            "hired vehicle",
            "rental car coverage",
        ],
        CoverageCategory.AUTO,
        "CA 00 01",
    ),
    "CA_NON_OWNED_AUTO": (
        "Non-Owned Auto Coverage",
        [
            "non-owned auto",
            "non owned auto",
            "nonowned auto",
            "employee auto",
        ],
        CoverageCategory.AUTO,
        "CA 00 01",
    ),
    "CA_TOWING": (
        "Towing And Labor Coverage",
        [
            "towing",
            "towing and labor",
            "tow coverage",
            "roadside assistance",
        ],
        CoverageCategory.AUTO,
        "CA 00 01",
    ),
    "CA_RENTAL_REIMBURSEMENT": (
        "Transportation Expenses Coverage",
        [
            "transportation expenses",
            "rental reimbursement",
            "loss of use",
            "substitute transportation",
        ],
        CoverageCategory.AUTO,
        "CA 00 01",
    ),
    "CA_GLASS": (
        "Glass Breakage Coverage",
        [
            "glass breakage",
            "glass coverage",
            "windshield coverage",
        ],
        CoverageCategory.AUTO,
        "CA 00 01",
    ),
    "CA_SUPPLEMENTARY_PAYMENTS": (
        "Supplementary Payments",
        [
            "supplementary payments",
            "supplementary",
            "supp payments",
        ],
        CoverageCategory.AUTO,
        "CA 00 01",
    ),
    "CA_OUT_OF_STATE": (
        "Out-Of-State Coverage Extensions",
        [
            "out-of-state",
            "out of state",
            "interstate coverage",
        ],
        CoverageCategory.AUTO,
        "CA 00 01",
    ),

    # ============= GENERAL LIABILITY COVERAGES (CG 00 01) =============
    "GL_COMBINED": (
        "Commercial General Liability",
        [
            "general liability",
            "commercial general liability",
            "cgl",
            "cgl coverage",
            "gl coverage",
        ],
        CoverageCategory.GENERAL_LIABILITY,
        "CG 00 01",
    ),
    "GL_PREMISES_OPS": (
        "Premises And Operations Liability",
        [
            "premises and operations",
            "premises/operations",
            "premises liability",
            "operations liability",
            "bodily injury and property damage",
            "coverage a",
        ],
        CoverageCategory.GENERAL_LIABILITY,
        "CG 00 01",
    ),
    "GL_PRODUCTS_COMPLETED_OPS": (
        "Products-Completed Operations Liability",
        [
            "products-completed operations",
            "products completed operations",
            "prod/comp ops",
            "products liability",
            "completed operations",
        ],
        CoverageCategory.GENERAL_LIABILITY,
        "CG 00 01",
    ),
    "GL_PERSONAL_ADVERTISING": (
        "Personal And Advertising Injury Liability",
        [
            "personal and advertising injury",
            "personal injury",
            "advertising injury",
            "coverage b",
        ],
        CoverageCategory.GENERAL_LIABILITY,
        "CG 00 01",
    ),
    "GL_MEDICAL_PAYMENTS": (
        "Medical Payments Coverage",
        [
            "medical payments",
            "med pay gl",
            "coverage c",
        ],
        CoverageCategory.GENERAL_LIABILITY,
        "CG 00 01",
    ),
    "GL_DAMAGE_TO_PREMISES": (
        "Damage To Premises Rented To You",
        [
            "damage to premises rented",
            "fire damage legal liability",
            "fire legal",
            "damage to rented premises",
        ],
        CoverageCategory.GENERAL_LIABILITY,
        "CG 00 01",
    ),
    "GL_SUPPLEMENTARY_PAYMENTS": (
        "Supplementary Payments - General Liability",
        [
            "supplementary payments gl",
            "supplementary payments - gl",
        ],
        CoverageCategory.GENERAL_LIABILITY,
        "CG 00 01",
    ),

    # ============= WORKERS COMPENSATION (WC 00 00) =============
    "WC_PART_A": (
        "Workers Compensation Insurance",
        [
            "workers compensation",
            "workers comp",
            "work comp",
            "wc coverage",
            "part one",
            "part a",
        ],
        CoverageCategory.WORKERS_COMP,
        "WC 00 00",
    ),
    "WC_PART_B": (
        "Employers Liability Insurance",
        [
            "employers liability",
            "employer's liability",
            "el coverage",
            "part two",
            "part b",
        ],
        CoverageCategory.WORKERS_COMP,
        "WC 00 00",
    ),
    "WC_COMBINED": (
        "Workers Compensation And Employers Liability",
        [
            "workers compensation and employers liability",
            "wc and el",
            "wc/el",
            "workers comp and employers liability",
            "wc el coverage",
        ],
        CoverageCategory.WORKERS_COMP,
        "WC 00 00",
    ),
    "WC_OTHER_STATES": (
        "Other States Coverage",
        [
            "other states",
            "other states coverage",
            "part three",
        ],
        CoverageCategory.WORKERS_COMP,
        "WC 00 00",
    ),
    "WC_VOLUNTARY_COMP": (
        "Voluntary Compensation Coverage",
        [
            "voluntary compensation",
            "voluntary comp",
        ],
        CoverageCategory.WORKERS_COMP,
        "WC 00 00",
    ),

    # ============= PROPERTY COVERAGES (CP 00 10, CP 00 30) =============
    "CP_BUILDING": (
        "Building Coverage",
        [
            "building",
            "building coverage",
            "structure coverage",
            "real property",
        ],
        CoverageCategory.PROPERTY,
        "CP 00 10",
    ),
    "CP_BPP": (
        "Business Personal Property Coverage",
        [
            "business personal property",
            "bpp",
            "contents",
            "personal property coverage",
        ],
        CoverageCategory.PROPERTY,
        "CP 00 10",
    ),
    "CP_BUSINESS_INCOME": (
        "Business Income Coverage",
        [
            "business income",
            "business interruption",
            "bi coverage",
            "loss of income",
        ],
        CoverageCategory.PROPERTY,
        "CP 00 30",
    ),
    "CP_EXTRA_EXPENSE": (
        "Extra Expense Coverage",
        [
            "extra expense",
            "additional expense",
        ],
        CoverageCategory.PROPERTY,
        "CP 00 30",
    ),
    "CP_EQUIPMENT_BREAKDOWN": (
        "Equipment Breakdown Coverage",
        [
            "equipment breakdown",
            "boiler and machinery",
            "mechanical breakdown",
        ],
        CoverageCategory.PROPERTY,
        "CP 00 10",
    ),

    # ============= UMBRELLA/EXCESS =============
    "UMB_FOLLOW_FORM": (
        "Umbrella Liability Coverage",
        [
            "umbrella",
            "umbrella liability",
            "excess liability",
            "follow form umbrella",
        ],
        CoverageCategory.UMBRELLA,
        None,
    ),
}


# Standard exclusion identifiers
EXCLUSION_TAXONOMY: Dict[str, Tuple[str, List[str], CoverageCategory, Optional[str]]] = {
    # ============= AUTO EXCLUSIONS (CA 00 01) =============
    "EXCL_CA_EXPECTED_INTENDED": (
        "Expected Or Intended Injury",
        [
            "expected or intended",
            "intentional injury",
            "intentional acts",
        ],
        CoverageCategory.AUTO,
        "CA 00 01",
    ),
    "EXCL_CA_CONTRACTUAL": (
        "Contractual Liability",
        [
            "contractual",
            "contractual liability",
            "assumed liability",
        ],
        CoverageCategory.AUTO,
        "CA 00 01",
    ),
    "EXCL_CA_WORKERS_COMP": (
        "Workers Compensation",
        [
            "workers compensation exclusion",
            "employee injury",
            "fellow employee",
        ],
        CoverageCategory.AUTO,
        "CA 00 01",
    ),
    "EXCL_CA_EMPLOYEE_OWNED": (
        "Employee Owned Auto",
        [
            "employee owned",
            "employee owned auto",
            "personal auto of employee",
        ],
        CoverageCategory.AUTO,
        "CA 00 01",
    ),
    "EXCL_CA_CARE_CUSTODY": (
        "Care Custody Or Control",
        [
            "care custody control",
            "care, custody, or control",
            "property in care",
        ],
        CoverageCategory.AUTO,
        "CA 00 01",
    ),
    "EXCL_CA_WAR": (
        "War",
        [
            "war",
            "war exclusion",
            "acts of war",
        ],
        CoverageCategory.AUTO,
        "CA 00 01",
    ),
    "EXCL_CA_RACING": (
        "Racing",
        [
            "racing",
            "racing exclusion",
            "speed contest",
        ],
        CoverageCategory.AUTO,
        "CA 00 01",
    ),

    # ============= GL EXCLUSIONS (CG 00 01) =============
    "EXCL_GL_EXPECTED_INTENDED": (
        "Expected Or Intended Injury",
        [
            "expected or intended injury",
            "intentional injury",
        ],
        CoverageCategory.GENERAL_LIABILITY,
        "CG 00 01",
    ),
    "EXCL_GL_CONTRACTUAL": (
        "Contractual Liability",
        [
            "contractual liability",
            "assumed under contract",
        ],
        CoverageCategory.GENERAL_LIABILITY,
        "CG 00 01",
    ),
    "EXCL_GL_LIQUOR": (
        "Liquor Liability",
        [
            "liquor liability",
            "alcoholic beverages",
        ],
        CoverageCategory.GENERAL_LIABILITY,
        "CG 00 01",
    ),
    "EXCL_GL_POLLUTION": (
        "Pollution",
        [
            "pollution",
            "pollution exclusion",
            "total pollution",
            "contaminants",
        ],
        CoverageCategory.GENERAL_LIABILITY,
        "CG 00 01",
    ),
    "EXCL_GL_AIRCRAFT_AUTO_WATERCRAFT": (
        "Aircraft Auto Or Watercraft",
        [
            "aircraft auto watercraft",
            "aircraft, auto, watercraft",
            "mobile equipment",
        ],
        CoverageCategory.GENERAL_LIABILITY,
        "CG 00 01",
    ),
    "EXCL_GL_PROFESSIONAL": (
        "Professional Services",
        [
            "professional services",
            "professional liability",
            "errors and omissions",
        ],
        CoverageCategory.GENERAL_LIABILITY,
        "CG 00 01",
    ),
    "EXCL_GL_EMPLOYERS_LIABILITY": (
        "Employers Liability",
        [
            "employers liability",
            "employee injury",
            "employment practices",
        ],
        CoverageCategory.GENERAL_LIABILITY,
        "CG 00 01",
    ),
    "EXCL_GL_DAMAGE_TO_PROPERTY": (
        "Damage To Property",
        [
            "damage to property",
            "property owned by insured",
            "property in care custody",
        ],
        CoverageCategory.GENERAL_LIABILITY,
        "CG 00 01",
    ),
    "EXCL_GL_DAMAGE_TO_YOUR_PRODUCT": (
        "Damage To Your Product",
        [
            "damage to your product",
            "your product",
        ],
        CoverageCategory.GENERAL_LIABILITY,
        "CG 00 01",
    ),
    "EXCL_GL_DAMAGE_TO_YOUR_WORK": (
        "Damage To Your Work",
        [
            "damage to your work",
            "your work",
            "faulty workmanship",
        ],
        CoverageCategory.GENERAL_LIABILITY,
        "CG 00 01",
    ),
    "EXCL_GL_RECALL": (
        "Recall Of Products",
        [
            "recall",
            "product recall",
            "recall of products",
        ],
        CoverageCategory.GENERAL_LIABILITY,
        "CG 00 01",
    ),
}


def _normalize_text(text: str) -> str:
    """Normalize text for comparison.

    Args:
        text: Raw text to normalize.

    Returns:
        Normalized lowercase text with extra whitespace removed.
    """
    # Lowercase
    text = text.lower()
    # Remove special characters except spaces and hyphens
    text = re.sub(r'[^\w\s-]', '', text)
    # Normalize whitespace
    text = ' '.join(text.split())
    return text


def get_canonical_coverage_id(coverage_name: str) -> Optional[str]:
    """Get the canonical coverage ID for a given coverage name.

    Args:
        coverage_name: The coverage name to look up.

    Returns:
        Canonical ID if found, None otherwise.
    """
    normalized = _normalize_text(coverage_name)

    # Try exact match first
    for canonical_id, (standard_name, variations, _, _) in COVERAGE_TAXONOMY.items():
        if _normalize_text(standard_name) == normalized:
            return canonical_id
        for variation in variations:
            if _normalize_text(variation) == normalized:
                return canonical_id

    # Try partial match (coverage name contains or is contained by variation)
    best_match = None
    best_score = 0

    for canonical_id, (standard_name, variations, _, _) in COVERAGE_TAXONOMY.items():
        all_variations = [standard_name] + variations
        for variation in all_variations:
            norm_var = _normalize_text(variation)

            # Check for containment
            if norm_var in normalized or normalized in norm_var:
                # Score based on match length ratio
                score = len(norm_var) / max(len(normalized), len(norm_var))
                if score > best_score:
                    best_score = score
                    best_match = canonical_id

    # Only return if score is above threshold
    if best_score >= 0.5:
        return best_match

    return None


def get_canonical_exclusion_id(exclusion_name: str) -> Optional[str]:
    """Get the canonical exclusion ID for a given exclusion name.

    Args:
        exclusion_name: The exclusion name to look up.

    Returns:
        Canonical ID if found, None otherwise.
    """
    normalized = _normalize_text(exclusion_name)

    # Try exact match first
    for canonical_id, (standard_name, variations, _, _) in EXCLUSION_TAXONOMY.items():
        if _normalize_text(standard_name) == normalized:
            return canonical_id
        for variation in variations:
            if _normalize_text(variation) == normalized:
                return canonical_id

    # Try partial match
    best_match = None
    best_score = 0

    for canonical_id, (standard_name, variations, _, _) in EXCLUSION_TAXONOMY.items():
        all_variations = [standard_name] + variations
        for variation in all_variations:
            norm_var = _normalize_text(variation)

            if norm_var in normalized or normalized in norm_var:
                score = len(norm_var) / max(len(normalized), len(norm_var))
                if score > best_score:
                    best_score = score
                    best_match = canonical_id

    if best_score >= 0.5:
        return best_match

    return None


def generate_canonical_id(
    entity_name: str,
    entity_type: str,
    category: Optional[CoverageCategory] = None,
) -> str:
    """Generate a canonical ID for an entity.

    If no match is found in the taxonomy, generates a normalized ID
    from the entity name.

    Args:
        entity_name: Name of the coverage or exclusion.
        entity_type: "coverage" or "exclusion".
        category: Optional category hint for ID prefix.

    Returns:
        Canonical ID string.
    """
    # Try to find in taxonomy first
    if entity_type.lower() == "coverage":
        canonical_id = get_canonical_coverage_id(entity_name)
        if canonical_id:
            return canonical_id
    elif entity_type.lower() == "exclusion":
        canonical_id = get_canonical_exclusion_id(entity_name)
        if canonical_id:
            return canonical_id

    # Generate normalized ID if not found
    # Format: {type_prefix}_{category}_{normalized_name}
    normalized = _normalize_text(entity_name)
    # Convert to snake_case
    normalized = re.sub(r'\s+', '_', normalized)
    normalized = re.sub(r'-', '_', normalized)
    # Truncate to reasonable length
    normalized = normalized[:50]

    if entity_type.lower() == "coverage":
        prefix = "cov"
    else:
        prefix = "excl"

    if category:
        return f"{prefix}_{category.value}_{normalized}"
    else:
        return f"{prefix}_{normalized}"


def get_coverage_category(coverage_name: str) -> CoverageCategory:
    """Determine the coverage category from name.

    Args:
        coverage_name: Coverage name to categorize.

    Returns:
        CoverageCategory enum value.
    """
    # First check if it's in taxonomy
    canonical_id = get_canonical_coverage_id(coverage_name)
    if canonical_id and canonical_id in COVERAGE_TAXONOMY:
        return COVERAGE_TAXONOMY[canonical_id][2]

    # Infer from keywords
    name_lower = coverage_name.lower()

    if any(kw in name_lower for kw in ["auto", "vehicle", "car", "motor"]):
        return CoverageCategory.AUTO
    elif any(kw in name_lower for kw in ["general liability", "premises", "products", "gl"]):
        return CoverageCategory.GENERAL_LIABILITY
    elif any(kw in name_lower for kw in ["workers", "compensation", "employers liability"]):
        return CoverageCategory.WORKERS_COMP
    elif any(kw in name_lower for kw in ["property", "building", "bpp", "business personal"]):
        return CoverageCategory.PROPERTY
    elif any(kw in name_lower for kw in ["umbrella", "excess"]):
        return CoverageCategory.UMBRELLA
    elif any(kw in name_lower for kw in ["professional", "e&o", "errors"]):
        return CoverageCategory.PROFESSIONAL
    elif any(kw in name_lower for kw in ["cyber", "data", "privacy"]):
        return CoverageCategory.CYBER
    elif any(kw in name_lower for kw in ["inland", "marine", "equipment"]):
        return CoverageCategory.INLAND_MARINE

    return CoverageCategory.UNKNOWN


def get_standard_coverage_name(canonical_id: str) -> Optional[str]:
    """Get the standard coverage name for a canonical ID.

    Args:
        canonical_id: The canonical identifier.

    Returns:
        Standard coverage name if found.
    """
    if canonical_id in COVERAGE_TAXONOMY:
        return COVERAGE_TAXONOMY[canonical_id][0]
    return None


def get_standard_exclusion_name(canonical_id: str) -> Optional[str]:
    """Get the standard exclusion name for a canonical ID.

    Args:
        canonical_id: The canonical identifier.

    Returns:
        Standard exclusion name if found.
    """
    if canonical_id in EXCLUSION_TAXONOMY:
        return EXCLUSION_TAXONOMY[canonical_id][0]
    return None
