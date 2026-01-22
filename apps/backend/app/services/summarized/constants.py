from typing import Dict, List, Set, Any

# Retrieval Service Constants
DOMAIN_KEYWORDS = {
    "policy": ["coverage", "insurance", "declarations", "insured"],
    "claim": ["loss", "incident", "damage", "adjuster", "claimant"],
    "premium": ["cost", "payment", "amount due", "total premium"],
    "coverage": ["limit", "deductible", "sublimit", "per occurrence"],
    "location": ["address", "property", "site", "premises"],
    "vehicle": ["auto", "automobile", "car", "VIN"],
    "endorsement": ["amendment", "change", "modification", "rider"],
}

TERM_MAPPINGS = {
    "insured": ["named insured", "policyholder", "client"],
    "carrier": ["insurance company", "insurer", "underwriter"],
    "broker": ["agent", "producer", "intermediary"],
    "TIV": ["total insured value", "insured value"],
    "SOV": ["schedule of values", "property schedule"],
    "GL": ["general liability", "CGL", "commercial general liability"],
    "WC": ["workers compensation", "workers comp"],
}

QUERY_SECTION_MAPPINGS = {
    # Policy & Identity
    "policy number": {"declarations": 0.45, "coverages": -0.20},
    "policy no": {"declarations": 0.45},
    "named insured": {"declarations": 0.45, "conditions": -0.10},
    "insured": {"declarations": 0.35},
    "effective date": {"declarations": 0.35, "sov": -0.10},
    "expiration date": {"declarations": 0.35},
    "inception date": {"declarations": 0.35},
    # Coverages, Limits & Deductibles
    "coverage limit": {"coverages": 0.40},
    "coverage": {"coverages": 0.20, "declarations": 0.05},
    "limit": {"coverages": 0.30, "sov": -0.10},
    "deductible": {"coverages": 0.40},
    "sublimit": {"coverages": 0.40},
    "retention": {"coverages": 0.30},
    # Financials
    "premium": {"premium_summary": 0.40, "declarations": 0.20},
    "cost": {"premium_summary": 0.30},
    "tax": {"premium_summary": 0.30},
    "fee": {"premium_summary": 0.25},
    # Exclusions & Conditions
    "exclusion": {"exclusions": 0.45, "coverages": -0.20},
    "not covered": {"exclusions": 0.45},
    "limitation": {"exclusions": 0.25},
    "condition": {"conditions": 0.45},
    "requirement": {"conditions": 0.35},
    "provision": {"conditions": 0.30},
    # Endorsements
    "endorsement": {"endorsements": 0.45},
    "amendment": {"endorsements": 0.40},
    "change": {"endorsements": 0.20},
    # Locations & Property (SOV)
    "location": {"sov": 0.40, "locations": 0.45, "schedule_of_values": 0.40},
    "property": {"sov": 0.40},
    "properties": {"sov": 0.40},
    "address": {"sov": 0.35, "declarations": 0.15, "locations": 0.40},
    "tiv": {"sov": 0.45},
    "total insured value": {"sov": 0.45},
    # Claims & Losses
    "claim": {"loss_run": 0.45, "notice_of_claim": 0.30},
    "loss": {"loss_run": 0.45, "notice_of_claim": 0.25},
    "losses": {"loss_run": 0.45},
    "history": {"loss_run": 0.30, "conditions": -0.10},
    "incident": {"loss_run": 0.25, "notice_of_claim": 0.35},
    "notice of claim": {"notice_of_claim": 0.50},
    "fnol": {"notice_of_claim": 0.50},
    # Vehicle & Driver
    "vehicle": {"vehicle_schedule": 0.45},
    "auto": {"vehicle_schedule": 0.40},
    "vin": {"vehicle_schedule": 0.50},
    "driver": {"driver_schedule": 0.45},
    "license": {"driver_schedule": 0.45},
    "accident": {"driver_schedule": 0.30, "loss_run": 0.20},
    # Definitions & Terminology
    "definition": {"definitions": 0.50},
    "defined": {"definitions": 0.45},
    "meaning": {"definitions": 0.40},
    "terminology": {"definitions": 0.40},
    "glossary": {"definitions": 0.45},
}

GENERAL_SECTION_BOOST = {
    "declarations": 0.03,
    "coverages": 0.02,
    "schedule_of_values": 0.02,
    "sov": 0.02,
    "loss_run": 0.02,
    "exclusions": 0.015,
    "conditions": 0.015,
    "locations": 0.015,
    "notice_of_claim": 0.015,
    "vehicle_schedule": 0.015,
    "driver_schedule": 0.015,
    "premium_summary": 0.01,
    "definitions": 0.01,
}

# Intent Classifier Constants
INTENT_RULES: Dict[str, Set[str]] = {
    "policy_identity": {"declarations", "endorsements"},
    "coverage_details": {"coverages", "endorsements"},
    "restrictions": {"exclusions", "conditions"},
    "property_risk": {"sov", "locations", "schedule_of_values"},
    "claims_history": {"loss_run", "notice_of_claim", "fnol"},
    "vehicle_risk": {"vehicle_schedule"},
    "driver_risk": {"driver_schedule"},
    "financials": {"premium_summary"},
    "terminology": {"definitions"},
    "endorsement_details": {"endorsements"},
}

INTENT_KEYWORD_MAP: Dict[str, str] = {
    # Identity
    "policy number": "policy_identity",
    "policy no": "policy_identity",
    "named insured": "policy_identity",
    "insured": "policy_identity",
    "effective date": "policy_identity",
    "expiration date": "policy_identity",
    "inception date": "policy_identity",
    "broker": "policy_identity",
    "producer": "policy_identity",
    # Coverage
    "coverage": "coverage_details",
    "limit": "coverage_details",
    "limits": "coverage_details",
    "deductible": "coverage_details",
    "sublimit": "coverage_details",
    "retention": "coverage_details",
    "is covered": "coverage_details",
    "is wind covered": "coverage_details",
    "is fire covered": "coverage_details",
    "endorsement": "coverage_details",
    "modified": "coverage_details",
    # Restrictions
    "exclusion": "restrictions",
    "not covered": "restrictions",
    "limitation": "restrictions",
    "void": "restrictions",
    "fraud": "restrictions",
    "misrepresentation": "restrictions",
    "flood": "restrictions",
    "condition": "restrictions",
    "requirement": "restrictions",
    # Property
    "tiv": "property_risk",
    "total insured value": "property_risk",
    "location": "property_risk",
    "property": "property_risk",
    "properties": "property_risk",
    "address": "property_risk",
    "masonry": "property_risk",
    "construction": "property_risk",
    "sov": "property_risk",
    "schedule of values": "property_risk",
    # Claims
    "claim": "claims_history",
    "loss": "claims_history",
    "incident": "claims_history",
    "history": "claims_history",
    "fnol": "claims_history",
    "notice of claim": "claims_history",
    # Vehicle
    "vehicle": "vehicle_risk",
    "vin": "vehicle_risk",
    "auto": "vehicle_risk",
    "year make model": "vehicle_risk",
    "garaging": "vehicle_risk",
    # Driver
    "driver": "driver_risk",
    "license": "driver_risk",
    "mvr": "driver_risk",
    "violation": "driver_risk",
    "accident": "driver_risk",
    # Financials
    "premium": "financials",
    "commission": "financials",
    "taxes": "financials",
    "fees": "financials",
    "base premium": "financials",
    # Terminology
    "definition": "terminology",
    "definitions": "terminology",
    "defined": "terminology",
    "meaning": "terminology",
    "terminology": "terminology",
    "glossary": "terminology",
    # Specific Endorsement Intent
    "endorsement": "endorsement_details",
    "amendment": "endorsement_details",
}

# Vector Template Service Constants
FIELD_MAPPINGS = {
    "policy_number": ["policy_number", "policy_no", "policy_id", "policy_number_value", "pol_no"],
    "named_insured": ["named_insured", "insured_name", "client_name", "entity_name", "policyholder"],
    "mailing_address": ["mailing_address", "insured_address", "address", "mailing_addr", "addr"],
    "policy_period_start": ["policy_period_start", "effective_date", "inception_date", "start_date", "eff_date"],
    "policy_period_end": ["policy_period_end", "expiration_date", "expiry_date", "end_date", "exp_date"],
    "producer_name": ["producer_name", "broker_name", "agent_name", "agency_name", "producer"],
    "premium_total": ["premium_total", "total_premium", "premium_amount", "amount_due", "total_amount"],
    "limit_occurrence": ["limit_occurrence", "per_occurrence", "occurrence_limit", "limit_amount", "limit"],
    "limit_aggregate": ["limit_aggregate", "aggregate_limit", "aggregate_amount", "aggregate"],
    "deductible_amount": ["deductible_amount", "deductible", "ded_amount", "deductible_value", "ded"],
    # Vehicle fields
    "vin": ["vin", "vehicle_identification_number", "serial_number"],
    "vehicle_id": ["vehicle_id", "id", "unit_number", "unit_no"],
    # Driver fields
    "driver_id": ["driver_id", "id", "driver_number"],
    "license_number": ["license_number", "driver_license", "dl_number"],
}

SECTION_KEYWORDS = {
    "declarations": ["policy", "insured", "coverage", "effective", "premium", "terms", "named insured", "policy number"],
    "coverages": ["limit", "coverage", "protection", "sublimit", "deductible"],
    "exclusions": ["exclusion", "not covered", "excluded", "exception", "limitation"],
    "endorsements": ["amendment", "change", "endorsement", "modification", "rider", "addendum"],
    "schedule_of_values": ["location", "property", "TIV", "total insured value", "address", "occupancy"],
    "sov": ["location", "property", "TIV", "total insured value", "address", "occupancy"],
    "loss_run": ["claim", "loss", "incident", "damage", "paid", "reserved", "incurred", "claims history", "past losses"],
    "premium_summary": ["premium", "payment", "cost", "charge", "fee", "amount", "commission", "taxes"],
    "conditions": ["condition", "requirement", "obligation", "provision", "clause"],
    "locations": ["location", "address", "physical address", "premises", "site"],
    "notice_of_claim": ["claim", "loss", "incident", "notice", "fnol", "report"],
    "fnol": ["claim", "loss", "incident", "notice", "fnol", "report"],
    "vehicle_schedule": ["vehicle", "vin", "auto", "car", "truck", "make", "model"],
    "driver_schedule": ["driver", "license", "full name", "violations", "accidents"],
    "definitions": ["definition", "defined", "meaning", "terminology", "glossary", "terms"],
}

TYPE_ALIASES = {
    "sov": "schedule_of_values",
    "loss_run": "loss_run",
    "premium": "premium_summary",
    "dec": "declarations",
    "fnol": "notice_of_claim",
    "first_notice_of_loss": "notice_of_claim",
    "schedule_of_values": "schedule_of_values",
    "location": "locations",
    "driver": "driver_schedule",
    "vehicle": "vehicle_schedule",
}
