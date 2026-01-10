from typing import Dict, Any
from datetime import datetime
from app.services.base_service import BaseService
from app.services.summarized.constants import FIELD_MAPPINGS, SECTION_KEYWORDS, TYPE_ALIASES


class VectorTemplateService(BaseService):
    """Service for generating deterministic, context-rich text from extracted data.
    
    Improvements:
    1. Richer context with semantic keywords
    2. Hierarchical information structure
    3. Cross-references and relationships
    4. Domain-specific terminology
    5. Normalized formatting
    6. Better handling of missing data
    """

    def __init__(self):
        """Initialize the enhanced template service."""
        super().__init__()
        
        # Extended field mappings with more aliases
        self.field_mappings = FIELD_MAPPINGS
        
        # Semantic keywords for each section type
        self.section_keywords = SECTION_KEYWORDS

    def get_field(self, data: Dict[str, Any], field_key: str, default: Any = None) -> Any:
        """Get a field from data using aliases with improved handling."""
        aliases = self.field_mappings.get(field_key, [field_key])
        
        for alias in aliases:
            value = data.get(alias)
            # More robust null checking
            if value is not None and str(value).strip() not in ["", "N/A", "null", "None", "nan"]:
                return value
        
        return default

    def format_currency(self, amount: Any, currency: str = "USD") -> str:
        """Format currency amounts consistently."""
        if amount is None:
            return "Not specified"
        
        try:
            # Convert to float and format
            amount_float = float(str(amount).replace(",", "").replace("$", "").replace("₹", ""))
            
            if currency == "USD":
                return f"${amount_float:,.2f}"
            elif currency == "INR":
                return f"₹{amount_float:,.2f}"
            else:
                return f"{amount_float:,.2f} {currency}"
        except (ValueError, TypeError):
            return str(amount)

    def format_date(self, date_value: Any) -> str:
        """Format dates consistently."""
        if not date_value:
            return "Not specified"
        
        # Handle various date formats
        if isinstance(date_value, datetime):
            return date_value.strftime("%Y-%m-%d")
        
        return str(date_value)

    def add_semantic_context(self, section_type: str, base_text: str) -> str:
        """Add semantic keywords to improve retrieval."""
        keywords = self.section_keywords.get(section_type, [])
        
        if keywords:
            # Add keywords as context at the end
            context_line = f"\nContext keywords: {', '.join(keywords)}"
            return base_text + context_line
        
        return base_text

    async def run(self, section_type: str, data: Dict[str, Any]) -> str:
        """Generate enhanced embedding-friendly text.
        
        Args:
            section_type: The type of section
            data: The extracted fields for this section
            
        Returns:
            Formatted text ready for embedding with rich context
        """
        normalized_type = section_type.lower().replace(" ", "_").strip()
        
        # Mapping to template methods
        mapped_type = TYPE_ALIASES.get(normalized_type, normalized_type)
        method_name = f"_template_{mapped_type}"
        
        if hasattr(self, method_name):
            base_text = getattr(self, method_name)(data)
        else:
            base_text = self._template_default(section_type, data)
        
        # Add semantic context using the original type for retrieval consistency
        enhanced_text = self.add_semantic_context(normalized_type, base_text)
        
        return enhanced_text

    def _template_declarations(self, data: Dict[str, Any]) -> str:
        """Template for policy declarations."""
        lines = ["Section: Declarations"]
        
        policy_num = self.get_field(data, "policy_number")
        if policy_num: lines.append(f"Policy Number: {policy_num}")
        
        insured = self.get_field(data, "named_insured")
        if insured: lines.append(f"Named Insured: {insured}")
        
        address = self.get_field(data, "mailing_address")
        if address: lines.append(f"Mailing Address: {address}")
        
        start = self.get_field(data, "policy_period_start")
        end = self.get_field(data, "policy_period_end")
        if start or end:
            lines.append(f"Policy Period: {self.format_date(start)} to {self.format_date(end)}")
        
        producer = self.get_field(data, "producer_name")
        if producer: lines.append(f"Producer: {producer}")
        
        forms = data.get("form_numbers") or data.get("forms")
        if forms: lines.append(f"Forms: {forms}")
        
        premium = self.get_field(data, "premium_total")
        if premium:
            currency = data.get("currency", "USD")
            lines.append(f"Total Premium: {self.format_currency(premium, currency)}")
        
        return "\n".join(lines)

    def _template_coverages(self, data: Dict[str, Any]) -> str:
        """Template for coverage information."""
        lines = ["Section: Coverage"]
        
        name = data.get("coverage_name") or data.get("name")
        if name: lines.append(f"Coverage Name: {name}")
        
        included = data.get("included", "Yes")
        lines.append(f"Included: {included}")
        
        per_occ = self.get_field(data, "limit_occurrence")
        if per_occ: lines.append(f"Per Occurrence Limit: {self.format_currency(per_occ)}")
        
        aggregate = self.get_field(data, "limit_aggregate")
        if aggregate: lines.append(f"Aggregate Limit: {self.format_currency(aggregate)}")
        
        ded = self.get_field(data, "deductible_amount")
        if ded:
            ded_type = data.get("deductible_type", "")
            lines.append(f"Deductible: {self.format_currency(ded)} ({ded_type})")
        
        sublimit_name = data.get("sublimit_name")
        sublimit_amount = data.get("sublimit_amount")
        if sublimit_name or sublimit_amount:
            lines.append(f"Sublimit: {sublimit_name or ''} {self.format_currency(sublimit_amount) if sublimit_amount else ''}")
        
        return "\n".join(lines)

    def _template_exclusions(self, data: Dict[str, Any]) -> str:
        """Template for policy exclusions."""
        lines = ["Section: Exclusion"]
        
        name = data.get("exclusion_name") or data.get("name")
        if name: lines.append(f"Exclusion Name: {name}")
        
        manuscript = data.get("manuscript", "No")
        lines.append(f"Manuscript: {manuscript}")
        
        clause = data.get("exclusion_clause") or data.get("description")
        if clause: lines.append(f"Clause Summary: {clause}")
        
        page = data.get("page_reference") or data.get("source_page")
        if page: lines.append(f"Source Page: {page}")
                
        return "\n".join(lines)

    def _template_endorsements(self, data: Dict[str, Any]) -> str:
        """Template for endorsements."""
        lines = ["Section: Endorsement"]
        
        num = data.get("endorsement_number")
        if num: lines.append(f"Endorsement Number: {num}")
        
        title = data.get("endorsement_title") or data.get("title")
        if title: lines.append(f"Title: {title}")
        
        date = data.get("endorsement_date") or data.get("effective_date")
        if date: lines.append(f"Effective Date: {self.format_date(date)}")
        
        summary = data.get("changes_summary") or data.get("summary")
        if summary: lines.append(f"Summary of Changes: {summary}")
        
        return "\n".join(lines)

    def _template_premium_summary(self, data: Dict[str, Any]) -> str:
        """Template for premium summary."""
        lines = ["Section: Premium Summary"]
        
        base = data.get("base_premium")
        if base: lines.append(f"Base Premium: {self.format_currency(base)}")
        
        comm = data.get("brokerage_commission")
        if comm: lines.append(f"Brokerage Commission: {self.format_currency(comm)}")
        
        tax = data.get("taxes_fees") or data.get("tax_amount")
        if tax: lines.append(f"Taxes and Fees: {self.format_currency(tax)}")
        
        total = self.get_field(data, "premium_total")
        if total: lines.append(f"Total Premium: {self.format_currency(total)}")
        
        plan = data.get("payment_plan")
        if plan: lines.append(f"Payment Plan: {plan}")
        
        rate = data.get("rate_per_100")
        if rate: lines.append(f"Rate per 100: {rate}")
        
        return "\n".join(lines)

    def _template_conditions(self, data: Dict[str, Any]) -> str:
        """Template for policy conditions."""
        lines = ["Section: Condition"]
        
        name = data.get("condition_name") or data.get("name")
        if name: lines.append(f"Condition Name: {name}")
        
        clause = data.get("condition_clause") or data.get("description")
        if clause: lines.append(f"Clause Summary: {clause}")
        
        return "\n".join(lines)

    def _template_schedule_of_values(self, data: Dict[str, Any]) -> str:
        """Template for Schedule of Values."""
        lines = ["Section: Schedule of Values"]
        
        loc_id = data.get("location_id") or data.get("loc_no")
        if loc_id: lines.append(f"Location ID: {loc_id}")
        
        address = data.get("full_address") or data.get("address")
        if address: lines.append(f"Address: {address}")
        
        lat = data.get("latitude")
        lng = data.get("longitude")
        if lat and lng: lines.append(f"Coordinates: {lat}, {lng}")
        
        building = data.get("building_value")
        if building: lines.append(f"Building Value: {self.format_currency(building)}")
        
        contents = data.get("contents_value")
        if contents: lines.append(f"Contents Value: {self.format_currency(contents)}")
        
        bi = data.get("business_income") or data.get("bi_value")
        if bi: lines.append(f"Business Income Value: {self.format_currency(bi)}")
        
        tiv = data.get("tiv") or data.get("total_insured_value")
        if tiv: lines.append(f"Total Insured Value: {self.format_currency(tiv)}")
        
        const = data.get("construction_type")
        if const: lines.append(f"Construction: {const}")
        
        occ = data.get("occupancy_class") or data.get("occupancy")
        if occ: lines.append(f"Occupancy: {occ}")
        
        year = data.get("year_built")
        if year: lines.append(f"Year Built: {year}")
        
        stories = data.get("stories") or data.get("number_of_stories")
        if stories: lines.append(f"Stories: {stories}")
        
        area = data.get("area_sqft") or data.get("square_footage")
        if area: lines.append(f"Area: {area} sqft")
        
        pc = data.get("protection_class")
        if pc: lines.append(f"Protection Class: {pc}")
        
        sprinklers = data.get("sprinklers")
        if sprinklers: lines.append(f"Sprinklers: {sprinklers}")
        
        alarms = data.get("alarms")
        if alarms: lines.append(f"Alarms: {alarms}")
        
        return "\n".join(lines)

    def _template_loss_run(self, data: Dict[str, Any]) -> str:
        """Template for Loss Run claims and history."""
        lines = ["Section: Loss Run"]
        
        claim_num = data.get("claim_number")
        if claim_num: lines.append(f"Claim Number: {claim_num}")
        
        policy_num = self.get_field(data, "policy_number")
        if policy_num: lines.append(f"Policy Number: {policy_num}")
        
        loss_date = data.get("date_of_loss")
        if loss_date: lines.append(f"Date of Loss: {self.format_date(loss_date)}")
        
        cause = data.get("cause_of_loss")
        if cause: lines.append(f"Cause of Loss: {cause}")
        
        status = data.get("status") or data.get("claim_status")
        if status: lines.append(f"Status: {status}")
        
        paid_indemnity = data.get("paid_indemnity")
        if paid_indemnity: lines.append(f"Paid Indemnity: {self.format_currency(paid_indemnity)}")
        
        paid_expense = data.get("paid_expense")
        if paid_expense: lines.append(f"Paid Expense: {self.format_currency(paid_expense)}")
        
        reserves = data.get("reserves") or data.get("reserved_amount")
        if reserves: lines.append(f"Reserves: {self.format_currency(reserves)}")
        
        incurred = data.get("incurred_total")
        if incurred: lines.append(f"Total Incurred: {self.format_currency(incurred)}")
        
        return "\n".join(lines)

    def _template_locations(self, data: Dict[str, Any]) -> str:
        """Template for locations."""
        lines = ["Section: Location"]
        
        num = data.get("location_number") or data.get("loc_no")
        if num: lines.append(f"Location Number: {num}")
        
        phys_addr = data.get("physical_address") or data.get("address")
        if phys_addr: lines.append(f"Physical Address: {phys_addr}")
        
        mail_addr = data.get("mailing_address")
        if mail_addr: lines.append(f"Mailing Address: {mail_addr}")
        
        interest = data.get("interest")
        if interest: lines.append(f"Interest: {interest}")
        
        year = data.get("year_built")
        if year: lines.append(f"Year Built: {year}")
        
        sqft = data.get("square_footage")
        if sqft: lines.append(f"Square Footage: {sqft}")
        
        return "\n".join(lines)

    def _template_notice_of_claim(self, data: Dict[str, Any]) -> str:
        """Template for First Notice of Loss / Notice of Claim."""
        lines = ["Section: First Notice of Loss"]
        
        policy_num = self.get_field(data, "policy_number")
        if policy_num: lines.append(f"Policy Number: {policy_num}")
        
        insured = self.get_field(data, "named_insured")
        if insured: lines.append(f"Named Insured: {insured}")
        
        claimant = data.get("claimant_name")
        if claimant: lines.append(f"Claimant: {claimant}")
        
        date = data.get("date_of_loss")
        time = data.get("time_of_loss")
        if date or time:
            lines.append(f"Date of Loss: {self.format_date(date)} {time or ''}")
        
        loc = data.get("loss_location")
        if loc: lines.append(f"Loss Location: {loc}")
        
        cause = data.get("cause_description") or data.get("description")
        if cause: lines.append(f"Cause Description: {cause}")
        
        amount = data.get("claimed_amount")
        if amount: lines.append(f"Claimed Amount: {self.format_currency(amount)}")
        
        police = data.get("police_report_number")
        if police: lines.append(f"Police Report: {police}")
        
        witnesses = data.get("witnesses")
        if witnesses: lines.append(f"Witnesses: {witnesses}")
        
        return "\n".join(lines)

    def _template_vehicle_schedule(self, data: Dict[str, Any]) -> str:
        """Template for Vehicle Schedule."""
        lines = ["Section: Vehicle Schedule"]
        
        v_id = self.get_field(data, "vehicle_id")
        if v_id: lines.append(f"Vehicle ID: {v_id}")
        
        vin = self.get_field(data, "vin")
        if vin: lines.append(f"VIN: {vin}")
        
        year = data.get("year")
        make = data.get("make")
        model = data.get("model")
        if year: lines.append(f"Year: {year}")
        if make: lines.append(f"Make: {make}")
        if model: lines.append(f"Model: {model}")
        
        v_type = data.get("vehicle_type")
        if v_type: lines.append(f"Vehicle Type: {v_type}")
        
        addr = data.get("garaging_address")
        if addr: lines.append(f"Garaging Address: {addr}")
        
        use = data.get("primary_use")
        if use: lines.append(f"Primary Use: {use}")
        
        radius = data.get("radius_operation")
        if radius: lines.append(f"Operating Radius: {radius}")
        
        return "\n".join(lines)

    def _template_driver_schedule(self, data: Dict[str, Any]) -> str:
        """Template for Driver Schedule."""
        lines = ["Section: Driver Schedule"]
        
        d_id = self.get_field(data, "driver_id")
        if d_id: lines.append(f"Driver ID: {d_id}")
        
        name = data.get("full_name") or data.get("name")
        if name: lines.append(f"Name: {name}")
        
        dob = data.get("date_of_birth")
        if dob: lines.append(f"Date of Birth: {self.format_date(dob)}")
        
        lic = self.get_field(data, "license_number")
        state = data.get("license_state")
        if lic: lines.append(f"License: {lic} ({state or 'Unknown State'})")
        
        exp = data.get("years_experience")
        if exp: lines.append(f"Years of Experience: {exp}")
        
        vio = data.get("violations_count")
        if vio: lines.append(f"Violations: {vio}")
        
        acc = data.get("accidents_count")
        if acc: lines.append(f"Accidents: {acc}")
        
        return "\n".join(lines)

    def _template_definitions(self, data: Dict[str, Any]) -> str:
        """Template for policy definitions."""
        lines = ["Section: Definitions"]
        
        term = data.get("term") or data.get("defined_term")
        if term: lines.append(f"Term: {term}")
        
        definition = data.get("definition") or data.get("meaning") or data.get("description")
        if definition: lines.append(f"Definition: {definition}")
        
        context = data.get("context") or data.get("applied_to")
        if context: lines.append(f"Context: {context}")
        
        return "\n".join(lines)

    def _template_default(self, section_type: str, data: Dict[str, Any]) -> str:
        """Default template with better structure."""
        lines = [
            f"Document Section: {section_type.replace('_', ' ').title()}",
            ""
        ]
        
        # Organize fields by importance
        important_fields = ["id", "number", "name", "date", "amount", "value"]
        other_fields = []
        
        for key, value in data.items():
            # Skip nested structures
            if key in ["entities", "coverages", "claims", "locations", "endorsements", "exclusions"]:
                continue
            
            # Skip empty values
            if value in [None, "", "N/A", "null", "None"]:
                continue
            
            # Check if important field
            is_important = any(imp in key.lower() for imp in important_fields)
            
            field_name = key.replace('_', ' ').title()
            field_value = value
            
            # Format specific types
            if isinstance(value, (int, float)) and 'amount' in key.lower():
                field_value = self.format_currency(value)
            elif 'date' in key.lower():
                field_value = self.format_date(value)
            
            line = f"{field_name}: {field_value}"
            
            if is_important:
                lines.insert(2, line)  # Add after header
            else:
                other_fields.append(line)
        
        # Add other fields at the end
        if other_fields:
            lines.append("")
            lines.extend(other_fields)
        
        return "\n".join(lines)