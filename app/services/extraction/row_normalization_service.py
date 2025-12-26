"""Row normalization service for converting table rows to domain objects.

This service converts structured table rows into SOVItem or LossRunClaim
domain objects, handling data type conversion and normalization.
"""

from typing import List, Dict, Any, Optional, Tuple
from decimal import Decimal
from datetime import datetime
import re

from app.services.extraction.table_extraction_service import TableStructure, ColumnMapping
from app.services.extraction.table_classification_service import TableClassification
from app.database.models import SOVItem, LossRunClaim
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class RowNormalizationService:
    """Service for normalizing table rows into domain objects.
    
    Converts raw table rows (list of strings) into structured
    SOVItem or LossRunClaim objects based on table type.
    """
    
    def __init__(self):
        """Initialize row normalization service."""
        LOGGER.info("Initialized RowNormalizationService")
    
    def normalize_rows(
        self,
        table: TableStructure,
        column_mappings: List[ColumnMapping],
        table_classification: TableClassification,
        document_id: Optional[str] = None
    ) -> List[Any]:
        """Normalize table rows into domain objects.
        
        Args:
            table: TableStructure with rows
            column_mappings: Column mappings from header canonicalization
            table_classification: Table classification result
            document_id: Optional document ID for linking
            
        Returns:
            List of SOVItem or LossRunClaim objects
        """
        if table_classification.table_type == "property_sov":
            return self._normalize_sov_rows(table, column_mappings, document_id)
        elif table_classification.table_type == "loss_run":
            return self._normalize_loss_run_rows(table, column_mappings, document_id)
        else:
            LOGGER.warning(
                f"Unknown table type for normalization: {table_classification.table_type}",
                extra={"table_id": table.table_id}
            )
            return []
    
    def _normalize_sov_rows(
        self,
        table: TableStructure,
        column_mappings: List[ColumnMapping],
        document_id: Optional[str]
    ) -> List[SOVItem]:
        """Normalize rows into SOVItem objects.
        
        Args:
            table: TableStructure
            column_mappings: Column mappings
            document_id: Document ID
            
        Returns:
            List of SOVItem objects
        """
        sov_items = []
        
        # Create mapping from column index to canonical field
        field_map = {m.index: m.canonical_field for m in column_mappings}
        
        # Log column mappings for debugging
        LOGGER.debug(
            f"Column mappings for table {table.table_id}",
            extra={
                "table_id": table.table_id,
                "headers": table.headers,
                "mappings": {idx: field for idx, field in field_map.items()},
                "total_columns": len(table.headers) if table.headers else 0,
                "mapped_columns": len(field_map)
            }
        )
        
        for row_idx, row in enumerate(table.rows):
            # Build row data dictionary
            row_data = {}
            for col_idx, cell_value in enumerate(row):
                if col_idx in field_map:
                    field_name = field_map[col_idx]
                    row_data[field_name] = cell_value
            
            # Log row data for debugging if no fields mapped
            if not row_data:
                LOGGER.debug(
                    f"No fields mapped for row {row_idx} in table {table.table_id}",
                    extra={
                        "table_id": table.table_id,
                        "row_index": row_idx,
                        "row_values": row[:5],  # First 5 cells
                        "column_mappings_count": len(field_map),
                        "headers": table.headers[:5] if table.headers else []
                    }
                )
            
            # Create SOVItem object
            sov_item = self._create_sov_item(row_data, document_id, row_idx)
            if sov_item:
                sov_items.append(sov_item)
            elif row_data:
                # Log why row was filtered out
                LOGGER.debug(
                    f"Row {row_idx} filtered out - no meaningful data",
                    extra={
                        "table_id": table.table_id,
                        "row_index": row_idx,
                        "row_data_keys": list(row_data.keys()),
                        "row_data_sample": {k: str(v)[:50] for k, v in list(row_data.items())[:3]}
                    }
                )
        
        LOGGER.info(
            f"Normalized {len(sov_items)} SOV rows from {len(table.rows)} total rows",
            extra={
                "table_id": table.table_id,
                "rows_processed": len(table.rows),
                "rows_normalized": len(sov_items),
                "mapped_columns": len(field_map),
                "headers": table.headers[:5] if table.headers else []
            }
        )
        
        return sov_items
    
    def _create_sov_item(
        self,
        row_data: Dict[str, str],
        document_id: Optional[str],
        row_index: int
    ) -> Optional[SOVItem]:
        """Create SOVItem from row data.
        
        Args:
            row_data: Dictionary of field values
            document_id: Document ID
            row_index: Row index
            
        Returns:
            SOVItem or None if invalid
        """
        try:
            # Extract and normalize values
            location_number = self._normalize_string(row_data.get("location"))
            building_number = self._normalize_string(row_data.get("building_number"))
            address = self._normalize_string(row_data.get("address"))
            description = self._normalize_string(row_data.get("description"))
            construction_type = self._normalize_string(row_data.get("construction_type"))
            occupancy = self._normalize_string(row_data.get("occupancy"))
            
            # Extract numeric values
            building_value = self._normalize_numeric(row_data.get("building_value"))
            contents_value = self._normalize_numeric(row_data.get("contents_value"))
            tenant_improvements = self._normalize_numeric(row_data.get("tenant_improvements"))
            business_income = self._normalize_numeric(row_data.get("business_income"))
            additional_property = self._normalize_numeric(row_data.get("additional_property"))
            tiv = self._normalize_numeric(row_data.get("tiv"))
            
            # Extract integer values
            year_built = self._normalize_integer(row_data.get("year_built"))
            square_footage = self._normalize_integer(row_data.get("square_footage"))
            
            # Extract property characteristics
            distance_to_coast = self._normalize_string(row_data.get("distance_to_coast"))
            flood_zone = self._normalize_string(row_data.get("flood_zone"))
            
            # Fix address mapping: detect if location_number contains an address
            location_number, address = self._fix_address_mapping(location_number, address, description)
            
            # Skip rows that are just headers or totals (no meaningful data)
            has_meaningful_data = any([
                building_value is not None,
                contents_value is not None,
                tiv is not None,
                address is not None,
                location_number is not None
            ])
            
            if not has_meaningful_data:
                LOGGER.debug(
                    f"Skipping row {row_index} - no meaningful data",
                    extra={"row_data": row_data}
                )
                return None
            
            # Calculate TIV if not provided but component values are
            if tiv is None:
                tiv = Decimal(0)
                if building_value is not None:
                    tiv += building_value
                if contents_value is not None:
                    tiv += contents_value
                if tenant_improvements is not None:
                    tiv += tenant_improvements
                if business_income is not None:
                    tiv += business_income
                if additional_property is not None:
                    tiv += additional_property
                if tiv == 0:
                    tiv = None
            
            # Create SOVItem
            sov_item = SOVItem(
                document_id=document_id,
                location_number=location_number or building_number,
                address=address,
                description=description if not address or description != address else None,
                construction_type=construction_type,
                occupancy=occupancy,
                year_built=year_built,
                square_footage=square_footage,
                building_limit=building_value,
                contents_limit=contents_value,
                bi_limit=business_income,
                total_insured_value=tiv,
                additional_data={
                    "row_index": row_index,
                    "source": "table_extraction",
                    "tenant_improvements": float(tenant_improvements) if tenant_improvements else None,
                    "additional_property": float(additional_property) if additional_property else None,
                    "distance_to_coast": distance_to_coast,
                    "flood_zone": flood_zone
                }
            )
            
            return sov_item
            
        except Exception as e:
            LOGGER.warning(
                f"Failed to create SOVItem from row data: {e}",
                extra={"row_index": row_index, "row_data": row_data}
            )
            return None
    
    def _normalize_loss_run_rows(
        self,
        table: TableStructure,
        column_mappings: List[ColumnMapping],
        document_id: Optional[str]
    ) -> List[LossRunClaim]:
        """Normalize rows into LossRunClaim objects.
        
        Args:
            table: TableStructure
            column_mappings: Column mappings
            document_id: Document ID
            
        Returns:
            List of LossRunClaim objects
        """
        claims = []
        
        # Create mapping from column index to canonical field
        field_map = {m.index: m.canonical_field for m in column_mappings}
        
        for row_idx, row in enumerate(table.rows):
            # Build row data dictionary
            row_data = {}
            for col_idx, cell_value in enumerate(row):
                if col_idx in field_map:
                    field_name = field_map[col_idx]
                    row_data[field_name] = cell_value
            
            # Create LossRunClaim object
            claim = self._create_loss_run_claim(row_data, document_id, row_idx)
            if claim:
                claims.append(claim)
        
        LOGGER.info(
            f"Normalized {len(claims)} loss run rows",
            extra={
                "table_id": table.table_id,
                "rows_processed": len(table.rows)
            }
        )
        
        return claims
    
    def _create_loss_run_claim(
        self,
        row_data: Dict[str, str],
        document_id: Optional[str],
        row_index: int
    ) -> Optional[LossRunClaim]:
        """Create LossRunClaim from row data.
        
        Args:
            row_data: Dictionary of field values
            document_id: Document ID
            row_index: Row index
            
        Returns:
            LossRunClaim or None if invalid
        """
        try:
            # Extract and normalize values
            claim_number = self._normalize_string(row_data.get("claim_number"))
            policy_number = self._normalize_string(row_data.get("policy_number"))
            insured_name = self._normalize_string(row_data.get("insured_name"))
            cause_of_loss = self._normalize_string(row_data.get("cause_of_loss"))
            description = self._normalize_string(row_data.get("description"))
            status = self._normalize_string(row_data.get("status"))
            
            # Extract dates
            loss_date = self._normalize_date(row_data.get("loss_date"))
            report_date = self._normalize_date(row_data.get("report_date"))
            
            # Extract numeric values
            incurred_amount = self._normalize_numeric(row_data.get("incurred_amount"))
            paid_amount = self._normalize_numeric(row_data.get("paid_amount"))
            reserve_amount = self._normalize_numeric(row_data.get("reserve_amount"))
            
            # Create LossRunClaim
            claim = LossRunClaim(
                document_id=document_id,
                claim_number=claim_number,
                policy_number=policy_number,
                insured_name=insured_name,
                loss_date=loss_date,
                report_date=report_date,
                cause_of_loss=cause_of_loss,
                description=description,
                incurred_amount=incurred_amount,
                paid_amount=paid_amount,
                reserve_amount=reserve_amount,
                status=status,
                additional_data={
                    "row_index": row_index,
                    "source": "table_extraction"
                }
            )
            
            return claim
            
        except Exception as e:
            LOGGER.warning(
                f"Failed to create LossRunClaim from row data: {e}",
                extra={"row_index": row_index, "row_data": row_data}
            )
            return None
    
    def _fix_address_mapping(
        self,
        location_number: Optional[str],
        address: Optional[str],
        description: Optional[str]
    ) -> Tuple[Optional[str], Optional[str]]:
        """Fix address mapping by detecting addresses in location_number.
        
        Sometimes addresses end up in location_number field. This method
        detects address patterns and moves them to the address field.
        
        Args:
            location_number: Location number value (may contain address)
            address: Address value (may be empty)
            description: Description value (may contain address)
            
        Returns:
            Tuple of (cleaned_location_number, cleaned_address)
        """
        import re
        
        # If address is already populated, use it
        if address:
            return location_number, address
        
        # Check if location_number contains an address pattern
        if location_number:
            # Address patterns: street numbers, street names, city/state/zip
            # Pattern: number + street name + city, state zip
            address_pattern = re.compile(
                r'\d+\s+[A-Z][A-Za-z\s]+(?:,\s*[A-Z][A-Za-z\s]+)?(?:\s+\d{5})?',
                re.IGNORECASE
            )
            
            # Check if location_number looks like an address
            if address_pattern.search(location_number):
                # Check if it's a full address (has city/state)
                if re.search(r',\s*[A-Z]{2}\s+\d{5}', location_number, re.IGNORECASE):
                    # Full address - move to address field
                    return None, location_number
                elif len(location_number) > 30:  # Likely an address if long
                    # Likely an address - move to address field
                    return None, location_number
        
        # Check description for address patterns
        if description and not address:
            address_pattern = re.compile(
                r'\d+\s+[A-Z][A-Za-z\s]+(?:,\s*[A-Z][A-Za-z\s]+)?(?:\s+\d{5})?',
                re.IGNORECASE
            )
            if address_pattern.search(description):
                # Check if description is primarily an address
                if re.search(r',\s*[A-Z]{2}\s+\d{5}', description, re.IGNORECASE):
                    # Use description as address
                    return location_number, description
        
        return location_number, address
    
    def _normalize_string(self, value: Optional[str]) -> Optional[str]:
        """Normalize string value.
        
        Args:
            value: Raw string value
            
        Returns:
            Normalized string or None
        """
        if value is None:
            return None
        
        value = str(value).strip()
        if not value or value.lower() in ["-", "n/a", "na", "none", ""]:
            return None
        
        return value
    
    def _normalize_numeric(self, value: Optional[str]) -> Optional[Decimal]:
        """Normalize numeric value.
        
        Args:
            value: Raw string value
            
        Returns:
            Decimal or None
        """
        if value is None:
            return None
        
        value = str(value).strip()
        if not value or value.lower() in ["-", "n/a", "na", "none", "", "included"]:
            return None
        
        # Remove currency symbols, commas, and other non-numeric characters
        # Keep only digits, decimal point, and minus sign
        cleaned = re.sub(r'[,$%]', '', value)  # Remove $, commas, %
        cleaned = re.sub(r'\s+', '', cleaned)  # Remove whitespace
        
        # Handle special cases like "15,564,194" or "$15,564,194"
        # Also handle numbers that might have spaces as thousand separators
        cleaned = re.sub(r'[^\d.\-]', '', cleaned)
        
        if not cleaned:
            return None
        
        try:
            return Decimal(cleaned)
        except Exception:
            LOGGER.debug(f"Failed to parse numeric value: {value} -> {cleaned}")
            return None
    
    def _normalize_integer(self, value: Optional[str]) -> Optional[int]:
        """Normalize integer value.
        
        Args:
            value: Raw string value
            
        Returns:
            Integer or None
        """
        if value is None:
            return None
        
        value = str(value).strip()
        if not value or value.lower() in ["-", "n/a", "na", "none", ""]:
            return None
        
        # Remove commas
        value = re.sub(r',', '', value)
        
        try:
            return int(float(value))  # Handle "2023.0" format
        except (ValueError, TypeError):
            LOGGER.debug(f"Failed to parse integer value: {value}")
            return None
    
    def _normalize_date(self, value: Optional[str]) -> Optional[datetime]:
        """Normalize date value.
        
        Args:
            value: Raw string value
            
        Returns:
            datetime.date or None
        """
        if value is None:
            return None
        
        value = str(value).strip()
        if not value or value.lower() in ["-", "n/a", "na", "none", ""]:
            return None
        
        # Try common date formats
        date_formats = [
            "%Y-%m-%d",
            "%m/%d/%Y",
            "%m-%d-%Y",
            "%d/%m/%Y",
            "%d-%m-%Y",
            "%Y/%m/%d",
        ]
        
        for fmt in date_formats:
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
        
        LOGGER.debug(f"Failed to parse date value: {value}")
        return None

