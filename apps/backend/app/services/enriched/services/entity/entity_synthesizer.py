"""Entity synthesis strategies for document sections.

This module implements the Strategy pattern for synthesizing entities from
extracted document data. Each section type has its own synthesis strategy.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type
import logging
from pydantic import ValidationError

from app.utils.canonical_key import slugify_entity_id

from app.schemas.graph import (
    PolicyNode,
    OrganizationNode,
    CoverageNode,
    ConditionNode,
    EndorsementNode,
    LocationNode,
    ClaimNode,
    DefinitionNode,
    OrganizationRole
)

LOGGER = logging.getLogger(__name__)


class EntitySynthesisStrategy(ABC):
    """Base strategy for synthesizing entities from extracted data."""
    
    @abstractmethod
    def synthesize(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Synthesize entities from extracted data.
        
        Args:
            data: Extracted data dictionary
            
        Returns:
            List of synthesized entity objects
        """
        pass

    def _get_extraction_block(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Get the structured extraction block from input data."""
        return (data.get("extracted_data") or 
                data.get("fields") or 
                data.get("attributes") or 
                data)

    def _validate_with_schema(self, node_class: Type, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and filter data using a GraphNode schema.
        
        Args:
            node_class: The Pydantic model class to validate against
            data: The attribute data to validate
            
        Returns:
            Validated attribute dictionary (only fields in schema)
        """
        try:
            node_data = data.copy()
            
            if "id" not in node_data:
                node_data["id"] = "temp_id"
                
            # Filter data to only include fields defined in the model
            model_fields = node_class.__fields__.keys()
            filtered_data = {k: v for k, v in node_data.items() if k in model_fields}
            
            # Validate
            node = node_class(**filtered_data)
            
            # Return as dict, excluding unset fields if desired (optional)
            validated = node.dict(exclude_none=True)
            
            # Remove the 'id' we added if it was temp
            if "id" in validated and validated["id"] == "temp_id":
                del validated["id"]
            
            return validated
            
        except ValidationError as e:
            LOGGER.warning(
                f"Validation filtered data for {node_class.__name__}: {e}",
                extra={"node_class": node_class.__name__, "errors": e.errors()}
            )
            # Fallback: return data but it might fail later
            return {k: v for k, v in data.items() if v is not None}
    
    def _create_entity(
        self,
        entity_type: str,
        identifier: str,
        confidence: float,
        attributes: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Helper to create standardized entity object.
        
        Args:
            entity_type: Entity type name
            identifier: Unique identifier for the entity
            confidence: Confidence score (0.0-1.0)
            attributes: Entity attributes
            
        Returns:
            Standardized entity dictionary
        """
        return {
            "type": entity_type,
            "id": identifier,
            "confidence": confidence,
            "attributes": attributes
        }
    
    def _normalize_id(self, text: str, prefix: str = "") -> str:
        """Normalize text for use as entity ID.
        
        Delegates to shared utility in app.utils.canonical_key.
        
        Args:
            text: Text to normalize
            prefix: Optional prefix for the ID
            
        Returns:
            Normalized identifier (slug)
        """
        return slugify_entity_id(text, prefix)
    
    def _get_nested_value(self, data: Dict[str, Any], *keys: str, default: Any = None) -> Any:
        """Safely get nested dictionary values.
        
        Args:
            data: Dictionary to search
            *keys: Sequence of keys to traverse
            default: Default value if key not found
            
        Returns:
            Value at nested key or default
        """
        current = data
        for key in keys:
            if isinstance(current, dict):
                current = current.get(key)
                if current is None:
                    return default
            else:
                return default
        return current if current is not None else default


class CoveragesStrategy(EntitySynthesisStrategy):
    """Strategy for synthesizing coverage entities."""
    
    def synthesize(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        extraction = self._get_extraction_block(data)
        items = extraction.get("coverages") or extraction.get("items") or []
        if not isinstance(items, list):
            items = [items]
        
        entities = []
        for item in items:
            if not isinstance(item, dict):
                continue
                
            # Get coverage name
            name = (item.get("coverage_name") or 
                   item.get("coverage_label") or 
                   item.get("name"))
            
            if name:
                # Map fields to match CoverageNode
                item_mapped = item.copy()
                item_mapped["name"] = name
                
                # Validate against schema
                attributes = self._validate_with_schema(CoverageNode, item_mapped)
                
                entities.append(self._create_entity(
                    entity_type="Coverage",
                    identifier=self._normalize_id(name, "cov"),
                    confidence=item.get("confidence", 0.9),
                    attributes=attributes
                ))
        
        return entities


class LimitsStrategy(EntitySynthesisStrategy):
    """Strategy for synthesizing limit entities."""
    
    def synthesize(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        items = data.get("limits") or data.get("items") or []
        if not isinstance(items, list):
            items = [items]
        
        entities = []
        for item in items:
            if not isinstance(item, dict):
                continue
                
            name = item.get("limit_name") or item.get("coverage_name") or item.get("name")
            if name:
                attributes = {
                    "limit_name": name,
                    "limit_amount": item.get("limit_amount") or item.get("amount"),
                    "limit_type": item.get("limit_type"),
                    "per_occurrence": item.get("per_occurrence"),
                    "aggregate": item.get("aggregate"),
                    "applies_to": item.get("applies_to"),
                }
                
                attributes = {k: v for k, v in attributes.items() if v is not None}
                
                entities.append(self._create_entity(
                    entity_type="Limit",
                    identifier=self._normalize_id(name, "lim"),
                    confidence=item.get("confidence", 0.9),
                    attributes=attributes
                ))
        
        return entities


class DeductiblesStrategy(EntitySynthesisStrategy):
    """Strategy for synthesizing deductible entities."""
    
    def synthesize(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        items = data.get("deductibles") or data.get("items") or []
        if not isinstance(items, list):
            items = [items]
        
        entities = []
        for item in items:
            if not isinstance(item, dict):
                continue
                
            name = item.get("deductible_name") or item.get("coverage_name") or item.get("name")
            if name:
                attributes = {
                    "deductible_name": name,
                    "deductible_amount": item.get("deductible_amount") or item.get("amount"),
                    "deductible_type": item.get("deductible_type"),
                    "per_occurrence": item.get("per_occurrence"),
                    "applies_to": item.get("applies_to"),
                    "description": item.get("description"),
                }
                
                attributes = {k: v for k, v in attributes.items() if v is not None}
                
                entities.append(self._create_entity(
                    entity_type="Deductible",
                    identifier=self._normalize_id(name, "ded"),
                    confidence=item.get("confidence", 0.9),
                    attributes=attributes
                ))
        
        return entities


class DefinitionsStrategy(EntitySynthesisStrategy):
    """Strategy for synthesizing definition entities."""
    
    def synthesize(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        extraction = self._get_extraction_block(data)
        items = extraction.get("definitions") or extraction.get("items") or []
        if not isinstance(items, list):
            items = [items]
        
        entities = []
        for item in items:
            if not isinstance(item, dict):
                continue
                
            term = item.get("term") or item.get("definition_term")
            if term:
                # Map fields to match DefinitionNode
                item_mapped = item.copy()
                item_mapped["term"] = term
                item_mapped["definition_text"] = item.get("definition_text") or item.get("definition")
                
                # Validate against schema
                attributes = self._validate_with_schema(DefinitionNode, item_mapped)
                
                entities.append(self._create_entity(
                    entity_type="Definition",
                    identifier=self._normalize_id(term, "def"),
                    confidence=item.get("confidence", 0.9),
                    attributes=attributes
                ))
        
        return entities


class ConditionsStrategy(EntitySynthesisStrategy):
    """Strategy for synthesizing condition entities."""
    
    def synthesize(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        extraction = self._get_extraction_block(data)
        items = extraction.get("conditions") or extraction.get("items") or []
        if not isinstance(items, list):
            items = [items]
        
        entities = []
        for item in items:
            if not isinstance(item, dict):
                continue
                
            title = item.get("title") or item.get("condition_title") or item.get("name")
            if title:
                # Map fields to match ConditionNode
                item_mapped = item.copy()
                item_mapped["title"] = title
                
                # Validate against schema
                attributes = self._validate_with_schema(ConditionNode, item_mapped)
                
                entities.append(self._create_entity(
                    entity_type="Condition",
                    identifier=self._normalize_id(title, "cond"),
                    confidence=item.get("confidence", 0.9),
                    attributes=attributes
                ))
        
        return entities


class ExclusionsStrategy(EntitySynthesisStrategy):
    """Strategy for synthesizing exclusion entities."""
    
    def synthesize(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        items = data.get("exclusions") or data.get("items") or []
        if not isinstance(items, list):
            items = [items]
        
        entities = []
        for item in items:
            if not isinstance(item, dict):
                continue
                
            title = item.get("title") or item.get("exclusion_title") or item.get("name")
            if title:
                attributes = {
                    "title": title,
                    "exclusion_type": item.get("exclusion_type"),
                    "description": item.get("description"),
                    "applies_to": item.get("applies_to"),
                    "exceptions": item.get("exceptions"),
                    "reference": item.get("reference"),
                }
                
                attributes = {k: v for k, v in attributes.items() if v is not None}
                
                entities.append(self._create_entity(
                    entity_type="Exclusion",
                    identifier=self._normalize_id(title, "excl"),
                    confidence=item.get("confidence", 0.9),
                    attributes=attributes
                ))
        
        return entities


class EndorsementsStrategy(EntitySynthesisStrategy):
    """Strategy for synthesizing endorsement entities."""
    
    def synthesize(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        extraction = self._get_extraction_block(data)
        items = extraction.get("endorsements") or extraction.get("items") or []
        if not isinstance(items, list):
            items = [items]
        
        entities = []
        for item in items:
            if not isinstance(item, dict):
                continue
                
            # Handle both dict with 'attributes' and direct dict
            if "attributes" in item:
                item_data = item["attributes"]
                base_confidence = item.get("confidence", 0.9)
            else:
                item_data = item
                base_confidence = item.get("confidence", 0.9)
            
            form_number = (item_data.get("form_number") or 
                          item_data.get("endorsement_number") or
                          item_data.get("number"))
            title = (item_data.get("title") or 
                    item_data.get("endorsement_title") or
                    item_data.get("name"))
            
            if form_number or title:
                identifier = form_number or title
                
                # Map fields to match EndorsementNode
                item_mapped = item_data.copy()
                item_mapped["title"] = title or form_number
                item_mapped["endorsement_number"] = form_number
                
                # Validate against schema
                attributes = self._validate_with_schema(EndorsementNode, item_mapped)
                
                entities.append(self._create_entity(
                    entity_type="Endorsement",
                    identifier=self._normalize_id(identifier, "end"),
                    confidence=base_confidence,
                    attributes=attributes
                ))
        
        return entities


class FormsStrategy(EntitySynthesisStrategy):
    """Strategy for synthesizing form entities."""
    
    def synthesize(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        items = data.get("forms") or data.get("items") or []
        if not isinstance(items, list):
            items = [items]
        
        entities = []
        for item in items:
            if not isinstance(item, dict):
                continue
                
            form_number = item.get("form_number") or item.get("number")
            if form_number:
                attributes = {
                    "form_number": form_number,
                    "form_name": item.get("form_name") or item.get("name"),
                    "edition_date": item.get("edition_date"),
                    "description": item.get("description"),
                }
                
                attributes = {k: v for k, v in attributes.items() if v is not None}
                
                entities.append(self._create_entity(
                    entity_type="Form",
                    identifier=self._normalize_id(form_number, "form"),
                    confidence=item.get("confidence", 0.9),
                    attributes=attributes
                ))
        
        return entities


class DeclarationsStrategy(EntitySynthesisStrategy):
    """Strategy for synthesizing entities from declarations section."""
    
    def synthesize(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        extraction = self._get_extraction_block(data)
        entities = []
        
        # Insured organization
        insured_name = extraction.get("insured_name")
        if insured_name:
            item_mapped = {
                "name": insured_name,
                "role": OrganizationRole.INSURED,
                "address": extraction.get("insured_address")
            }
            attributes = self._validate_with_schema(OrganizationNode, item_mapped)
            
            entities.append(self._create_entity(
                entity_type="Organization",
                identifier=self._normalize_id(insured_name, "org"),
                confidence=0.97,
                attributes=attributes
            ))
        
        # Carrier organization
        carrier_name = extraction.get("carrier_name")
        if carrier_name:
            item_mapped = {
                "name": carrier_name,
                "role": OrganizationRole.CARRIER
            }
            attributes = self._validate_with_schema(OrganizationNode, item_mapped)
            
            entities.append(self._create_entity(
                entity_type="Organization",
                identifier=self._normalize_id(carrier_name, "org"),
                confidence=0.95,
                attributes=attributes
            ))
        
        # Broker organization
        broker_name = extraction.get("broker_name")
        if broker_name:
            item_mapped = {
                "name": broker_name,
                "role": OrganizationRole.BROKER
            }
            attributes = self._validate_with_schema(OrganizationNode, item_mapped)
            
            entities.append(self._create_entity(
                entity_type="Organization",
                identifier=self._normalize_id(broker_name, "org"),
                confidence=0.90,
                attributes=attributes
            ))
        
        # Policy entity
        policy_number = extraction.get("policy_number")
        if policy_number:
            # Map all available policy fields, ensuring total_premium is captured
            item_mapped = extraction.copy()
            item_mapped["policy_number"] = policy_number
            # Ensure price fields are captured correctly
            item_mapped["total_premium"] = extraction.get("total_premium")
            item_mapped["base_premium"] = extraction.get("base_premium")
            
            attributes = self._validate_with_schema(PolicyNode, item_mapped)
            
            entities.append(self._create_entity(
                entity_type="Policy",
                identifier=self._normalize_id(policy_number, "policy"),
                confidence=0.96,
                attributes=attributes
            ))
        
        # Location entity (mailing address)
        insured_address = extraction.get("insured_address")
        if insured_address:
            item_mapped = {
                "address": insured_address,
                "source_section": "declarations"
            }
            attributes = self._validate_with_schema(LocationNode, item_mapped)
            
            address_id = insured_address.split('\n')[0].split(',')[0]
            
            entities.append(self._create_entity(
                entity_type="Location",
                identifier=self._normalize_id(address_id, "loc"),
                confidence=0.95,
                attributes=attributes
            ))
        
        return entities


class SOVStrategy(EntitySynthesisStrategy):
    """Strategy for synthesizing entities from Schedule of Values."""
    
    def synthesize(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        extraction = self._get_extraction_block(data)
        entities = []
        
        # Handle nested SOV structure
        sov_data = extraction.get("statement_of_values", extraction)
        
        # Get locations from various possible keys
        items = (sov_data.get("locations") or 
                sov_data.get("properties") or 
                sov_data.get("items") or [])
        
        if not isinstance(items, list):
            items = [items]
        
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            
            # Get location identifier
            location_id = (item.get("location_id") or 
                          item.get("location_number") or
                          item.get("bldg") or
                          item.get("building_number") or
                          f"location_{idx + 1}")
            
            # Get description/address
            address = (item.get("address") or 
                      item.get("location_description") or
                      item.get("description"))
            
            if location_id or address:
                identifier = address if address else str(location_id)
                
                # Map fields to match LocationNode
                item_mapped = item.copy()
                item_mapped["location_id"] = str(location_id)
                item_mapped["address"] = address or "Unknown Address"
                # Map value fields
                item_mapped["building_value"] = item.get("building") or item.get("building_value")
                item_mapped["contents_value"] = item.get("business_personal_property") or item.get("contents_value")
                item_mapped["bi_value"] = item.get("business_income_and_extra_expense") or item.get("bi_value")
                item_mapped["tiv"] = item.get("total_values") or item.get("tiv")
                
                # Validate against schema
                attributes = self._validate_with_schema(LocationNode, item_mapped)
                
                entities.append(self._create_entity(
                    entity_type="Location",
                    identifier=self._normalize_id(str(identifier), "loc"),
                    confidence=item.get("confidence", 0.9),
                    attributes=attributes
                ))
        
        return entities


class LossRunsStrategy(EntitySynthesisStrategy):
    """Strategy for synthesizing entities from loss runs."""
    
    def synthesize(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        extraction = self._get_extraction_block(data)
        items = extraction.get("claims") or extraction.get("losses") or extraction.get("items") or []
        if not isinstance(items, list):
            items = [items]
        
        entities = []
        for item in items:
            if not isinstance(item, dict):
                continue
                
            claim_number = item.get("claim_number") or item.get("loss_number")
            if claim_number:
                # Map fields to match ClaimNode
                item_mapped = item.copy()
                item_mapped["claim_number"] = claim_number
                item_mapped["cause_of_loss"] = item.get("loss_type") or item.get("cause_of_loss")
                item_mapped["loss_date"] = item.get("loss_date") or item.get("date_of_loss")
                item_mapped["reported_date"] = item.get("reported_date") or item.get("report_date")
                
                # Validate against schema
                attributes = self._validate_with_schema(ClaimNode, item_mapped)
                
                entities.append(self._create_entity(
                    entity_type="Claim",
                    identifier=self._normalize_id(claim_number, "clm"),
                    confidence=item.get("confidence", 0.9),
                    attributes=attributes
                ))
        
        return entities


class ScheduleStrategy(EntitySynthesisStrategy):
    """Generic strategy for schedule-based sections (vehicles, drivers, etc)."""
    
    def __init__(self, entity_type: str, id_prefix: str, key_fields: List[str]):
        """Initialize schedule strategy.
        
        Args:
            entity_type: Type of entity to create
            id_prefix: Prefix for entity IDs
            key_fields: List of field names to try as primary identifier (in order)
        """
        self.entity_type = entity_type
        self.id_prefix = id_prefix
        self.key_fields = key_fields if isinstance(key_fields, list) else [key_fields]
    
    def synthesize(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        items = data.get("items") or data.get(f"{self.entity_type.lower()}s") or []
        if not isinstance(items, list):
            items = [items]
        
        entities = []
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
                
            # Try to get identifier from key fields in order
            identifier = None
            for field in self.key_fields:
                identifier = item.get(field)
                if identifier:
                    break
            
            # Fall back to index if no identifier found
            if not identifier:
                identifier = f"item_{idx + 1}"
            
            entities.append(self._create_entity(
                entity_type=self.entity_type,
                identifier=self._normalize_id(str(identifier), self.id_prefix),
                confidence=item.get("confidence", 0.9),
                attributes=item
            ))
        
        return entities


class GeneralInfoStrategy(EntitySynthesisStrategy):
    """Strategy for general information sections."""
    
    def synthesize(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        entities = []
        
        # Extract key organizations
        org_fields = [
            ("insured_name", "insured"),
            ("broker_name", "broker"),
            ("agent_name", "agent"),
            ("producer_name", "producer"),
            ("carrier_name", "carrier"),
        ]
        
        for field_name, role in org_fields:
            org_name = data.get(field_name)
            if org_name:
                entities.append(self._create_entity(
                    entity_type="Organization",
                    identifier=self._normalize_id(org_name, "org"),
                    confidence=0.9,
                    attributes={"name": org_name, "role": role}
                ))
        
        return entities


class EntitySynthesisStrategyFactory:
    """Factory for creating entity synthesis strategies."""
    
    def __init__(self):
        """Initialize the factory with all strategies."""
        self._strategies: Dict[str, EntitySynthesisStrategy] = {
            # Policy sections
            "declarations": DeclarationsStrategy(),
            "coverages": CoveragesStrategy(),
            "limits": LimitsStrategy(),
            "deductibles": DeductiblesStrategy(),
            "conditions": ConditionsStrategy(),
            "exclusions": ExclusionsStrategy(),
            "definitions": DefinitionsStrategy(),
            "endorsements": EndorsementsStrategy(),
            "forms": FormsStrategy(),
            
            # Tables and schedules
            "sov": SOVStrategy(),
            "schedule_of_values": SOVStrategy(),
            "statement_of_values": SOVStrategy(),
            "loss_runs": LossRunsStrategy(),
            "premium_schedule": ScheduleStrategy("Premium", "prem", ["coverage_name", "name"]),
            "rate_schedule": ScheduleStrategy("Rate", "rate", ["coverage_name", "name"]),
            "vehicle_schedule": ScheduleStrategy("Vehicle", "veh", ["vin", "vehicle_number", "unit"]),
            "driver_schedule": ScheduleStrategy("Driver", "drv", ["license_number", "driver_name", "name"]),
            
            # Submission and admin
            "general_info": GeneralInfoStrategy(),
            "application": GeneralInfoStrategy(),
            "acord": GeneralInfoStrategy(),
            "broker_letter": GeneralInfoStrategy(),
            "underwriting_notes": GeneralInfoStrategy(),
        }
    
    def get_strategy(self, section_type: str) -> Optional[EntitySynthesisStrategy]:
        """Get synthesis strategy for a section type.
        
        Args:
            section_type: Type of document section
            
        Returns:
            Strategy instance or None if not found
        """
        return self._strategies.get(section_type)
    
    def register_strategy(
        self,
        section_type: str,
        strategy: EntitySynthesisStrategy
    ) -> None:
        """Register a custom strategy for a section type.
        
        Args:
            section_type: Type of document section
            strategy: Strategy instance
        """
        self._strategies[section_type] = strategy
    
    def get_supported_types(self) -> List[str]:
        """Get list of supported section types.
        
        Returns:
            List of section type names
        """
        return list(self._strategies.keys())


class EntitySynthesizer:
    """Main entity synthesizer using strategy pattern."""
    
    def __init__(self):
        """Initialize the synthesizer with strategy factory."""
        self.factory = EntitySynthesisStrategyFactory()
    
    def synthesize_entities_from_data(
        self,
        extracted_fields: Dict[str, Any],
        section_type: str
    ) -> List[Dict[str, Any]]:
        """Synthesize entities from extracted_data when entities field is empty.
        
        This handles cases where the LLM extraction returned structured items
        but didn't populate the discrete 'entities' list.
        
        Args:
            extracted_fields: Full extracted fields from database
            section_type: Type of section
            
        Returns:
            List of synthesized entity objects
        """
        
        if not extracted_fields:
            LOGGER.debug(
                f"No extracted data found for section type: {section_type}",
                extra={"section_type": section_type}
            )
            return []
        
        # Get appropriate strategy
        strategy = self.factory.get_strategy(section_type)
        
        if not strategy:
            LOGGER.warning(
                f"No synthesis strategy found for section type: {section_type}",
                extra={
                    "section_type": section_type,
                    "supported_types": self.factory.get_supported_types()
                }
            )
            return []
        
        # Synthesize entities using strategy
        try:
            synthesized = strategy.synthesize(extracted_fields)
            
            if synthesized:
                LOGGER.info(
                    f"Synthesized {len(synthesized)} entities from extracted_data",
                    extra={
                        "section_type": section_type,
                        "synthesized_count": len(synthesized),
                        "entity_types": list(set(e["type"] for e in synthesized))
                    }
                )
            else:
                LOGGER.debug(
                    f"No entities synthesized for section type: {section_type}",
                    extra={"section_type": section_type, "data_keys": list(extracted_fields.keys())}
                )
            
            return synthesized
            
        except Exception as e:
            LOGGER.error(
                f"Error synthesizing entities for {section_type}: {e}",
                extra={"section_type": section_type, "error": str(e)},
                exc_info=True
            )
            return []
    
    def register_custom_strategy(
        self,
        section_type: str,
        strategy: EntitySynthesisStrategy
    ) -> None:
        """Register a custom synthesis strategy.
        
        Args:
            section_type: Type of document section
            strategy: Strategy instance
        """
        self.factory.register_strategy(section_type, strategy)