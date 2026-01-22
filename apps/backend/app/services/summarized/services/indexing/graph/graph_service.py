"""GraphRAG knowledge graph construction service."""

import uuid
import json
from typing import List, Dict, Any, Optional
from neo4j import AsyncDriver
from sqlalchemy.ext.asyncio import AsyncSession as SQLAlchemySession

from app.services.base_service import BaseService
from app.repositories.entity_repository import EntityRepository, EntityRelationshipRepository
from app.repositories.vector_embedding_repository import VectorEmbeddingRepository
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class GraphService(BaseService):
    """Constructs workflow-scoped knowledge graphs in Neo4j."""

    def __init__(
        self, 
        neo4j_driver: AsyncDriver, 
        db_session: SQLAlchemySession
    ):
        """Initialize service with Neo4j and DB sessions."""
        super().__init__()
        self.neo4j_driver = neo4j_driver
        self.db_session = db_session
        self.entity_repo = EntityRepository(db_session)
        self.rel_repo = EntityRelationshipRepository(db_session)
        self.emb_repo = VectorEmbeddingRepository(db_session)

    async def run(
        self, 
        workflow_id: str,
        document_id: Optional[str] = None
    ) -> Dict[str, int]:
        """Run the knowledge graph construction.
        
        Args:
            workflow_id: The ID of the workflow to scope the graph to.
            document_id: Optional ID of a specific document to restrict fetching.
            
        Returns:
            Dictionary with construction statistics.
        """
        LOGGER.info(
            "Starting knowledge graph construction",
            extra={
                "workflow_id": str(workflow_id),
                "document_id": str(document_id) if document_id else "all"
            }
        )

        stats = {
            "entities_created": 0,
            "relationships_created": 0,
            "embeddings_linked": 0,
            "errors": 0
        }

        try:
            # Convert to UUIDs for repo calls
            wf_uuid = uuid.UUID(workflow_id) if isinstance(workflow_id, str) else workflow_id
            doc_uuid = uuid.UUID(document_id) if document_id and isinstance(document_id, str) else document_id

            # Step 1: Fetch entities
            if doc_uuid:
                entities_with_prov = await self.entity_repo.get_with_provenance_by_document(doc_uuid)
            else:
                entities_with_prov = await self.entity_repo.get_with_provenance_by_workflow(wf_uuid)

            # Deduplicate by entity.id to avoid multiple nodes for multi-mention entities
            processed_entity_ids = set()
            for entity, source_chunk_id, source_section in entities_with_prov:
                if entity.id in processed_entity_ids:
                    continue
                    
                try:
                    await self._create_entity_node(entity, wf_uuid, source_chunk_id, source_section)
                    stats["entities_created"] += 1
                    processed_entity_ids.add(entity.id)
                except Exception as e:
                    LOGGER.error(
                        f"Failed to create entity node: {e}",
                        extra={"entity_id": str(entity.id)}
                    )
                    stats["errors"] += 1

            # Step 2: Fetch and create relationships
            if doc_uuid:
                relationships = await self.rel_repo.get_by_document(doc_uuid)
            else:
                relationships = await self.rel_repo.get_by_workflow(wf_uuid)

            for rel in relationships:
                try:
                    await self._create_relationship_edge(rel, wf_uuid)
                    stats["relationships_created"] += 1
                except Exception as e:
                    LOGGER.error(
                        f"Failed to create relationship: {e}",
                        extra={"relationship_id": str(rel.id)}
                    )
                    stats["errors"] += 1

            # Step 3: Fetch and create embeddings (optional/linked)
            if doc_uuid:
                embeddings = await self.emb_repo.get_by_document(doc_uuid)
                for emb in embeddings:
                    try:
                        await self._create_embedding_node(emb, wf_uuid)
                        stats["embeddings_linked"] += 1
                    except Exception as e:
                        LOGGER.error(
                            f"Failed to link embedding: {e}",
                            extra={"embedding_id": str(emb.id)}
                        )
                        stats["errors"] += 1

            LOGGER.info(
                "Knowledge graph construction completed",
                extra={
                    "workflow_id": str(workflow_id),
                    "stats": stats
                }
            )

            return stats

        except Exception as e:
            LOGGER.error(
                "Knowledge graph construction failed",
                exc_info=True,
                extra={"workflow_id": str(workflow_id)}
            )
            raise

    async def _create_entity_node(
        self,
        entity: Any,
        workflow_id: uuid.UUID,
        source_chunk_id: Optional[str] = None,
        source_section: Optional[str] = None
    ) -> None:
        """Create Neo4j node with proper type label and provenance."""
        
        # Map entity_type to node label
        node_label = entity.entity_type
        
        # Extract schema-specific properties from attributes
        properties = self._map_entity_properties(entity)
        properties["id"] = entity.canonical_key
        properties["workflow_id"] = str(workflow_id)
        
        if source_chunk_id:
            properties["source_chunk_id"] = source_chunk_id
        if source_section:
            properties["source_section"] = source_section.lower()
        
        # Build property string for SET clause
        set_clauses = ", ".join([f"n.{key} = ${key}" for key in properties.keys()])
        
        cypher = f"""
        MERGE (n:{node_label} {{id: $id, workflow_id: $workflow_id}})
        SET {set_clauses}
        RETURN n
        """
        
        await self.neo4j_driver.execute_query(cypher, properties)

    def _map_entity_properties(self, entity: Any) -> Dict[str, Any]:
        """Map entity attributes to schema-defined properties."""
        
        attrs = entity.attributes or {}
        entity_type = entity.entity_type
        
        # Base properties
        props = {
            "id": entity.canonical_key,
            "created_at": entity.created_at.isoformat() if hasattr(entity, 'created_at') else None
        }
        
        # Type-specific mappings
        if entity_type == "Policy":
            props.update({
                "policy_number": attrs.get("policy_number"),
                "policy_type": attrs.get("policy_type"),
                "policy_form": attrs.get("policy_form"),
                "status": attrs.get("status"),
                "effective_date": attrs.get("effective_date"),
                "expiration_date": attrs.get("expiration_date"),
                "policy_term": attrs.get("policy_term"),
                "total_premium": attrs.get("total_premium"),
                "base_premium": attrs.get("base_premium"),
                "rate_per_100": attrs.get("rate_per_100"),
            })
        
        elif entity_type == "Organization":
            props.update({
                "name": attrs.get("name"),
                "role": attrs.get("role"),
                "address": attrs.get("address"),
            })
        
        elif entity_type == "Coverage":
            props.update({
                "name": attrs.get("name"),
                "coverage_type": attrs.get("coverage_type"),
                "coverage_part": attrs.get("coverage_part"),
                "description": attrs.get("description"),
                "per_occurrence_limit": attrs.get("per_occurrence_limit"),
                "aggregate_limit": attrs.get("aggregate_limit"),
                "deductible_amount": attrs.get("deductible", attrs.get("deductible_amount")),
                "deductible_type": attrs.get("deductible_type"),
                "waiting_period": attrs.get("waiting_period"),
                "coinsurance": attrs.get("coinsurance"),
                "valuation_method": attrs.get("valuation_method"),
                "included": attrs.get("included"),
            })
        
        elif entity_type == "Condition":
            props.update({
                "title": attrs.get("title") or attrs.get("name"),
                "condition_type": attrs.get("condition_type"),
                "description": attrs.get("description"),
                "applies_to": attrs.get("applies_to"),
                "requirements": attrs.get("requirements"),
                "consequences": attrs.get("consequences"),
            })

        elif entity_type == "Endorsement":
            props.update({
                "endorsement_number": attrs.get("form_number", attrs.get("endorsement_number")),
                "title": attrs.get("title") or attrs.get("name"),
                "description": attrs.get("description"),
                "effective_date": attrs.get("effective_date"),
            })
        
        elif entity_type == "Location":
            props.update({
                "location_id": attrs.get("location_id"),
                "address": attrs.get("address"),
                "construction_type": attrs.get("construction_type"),
                "occupancy": attrs.get("occupancy"),
                "year_built": attrs.get("year_built"),
                "number_of_stories": attrs.get("number_of_stories"),
                "sprinklered": attrs.get("sprinklered"),
                "building_value": attrs.get("building_value"),
                "contents_value": attrs.get("contents_value"),
                "bi_value": attrs.get("bi_value"),
                "tiv": attrs.get("tiv"),
                "flood_zone": attrs.get("flood_zone"),
            })
        
        elif entity_type == "Claim":
            props.update({
                "claim_number": attrs.get("claim_number"),
                "cause_of_loss": attrs.get("cause_of_loss"),
                "status": attrs.get("status"),
                "loss_date": attrs.get("loss_date"),
                "report_date": attrs.get("report_date") or attrs.get("reported_date"),
                "paid_amount": attrs.get("paid_amount"),
                "incurred_amount": attrs.get("incurred_amount"),
                "reserve_amount": attrs.get("reserve_amount"),
                "description": attrs.get("description"),
            })

        elif entity_type == "Definition":
            props.update({
                "term": attrs.get("term"),
                "definition_text": attrs.get("definition_text") or attrs.get("definition"),
            })

        elif entity_type == "Vehicle":
            props.update({
                "vin": attrs.get("vin"),
                "year": attrs.get("year"),
                "make": attrs.get("make"),
                "model": attrs.get("model"),
            })

        elif entity_type == "Driver":
            props.update({
                "name": attrs.get("name"),
                "date_of_birth": attrs.get("date_of_birth"),
                "license_number": attrs.get("license_number"),
                "violations": attrs.get("violations"),
                "accidents": attrs.get("accidents"),
            })
        
        # Remove None values
        return {k: v for k, v in props.items() if v is not None}

    async def _create_relationship_edge(
        self,
        rel: Any,
        workflow_id: str
    ) -> None:
        """Create Neo4j edge for relationship."""

        # Get source and target entities from DB to get their canonical keys
        source = await self.entity_repo.get_by_id(rel.source_entity_id)
        target = await self.entity_repo.get_by_id(rel.target_entity_id)

        if not source or not target:
            LOGGER.warning(
                "Source or target entity not found",
                extra={
                    "source_id": str(rel.source_entity_id),
                    "target_id": str(rel.target_entity_id)
                }
            )
            return

        # Create relationship with proper type
        # Sanitize relationship type for Cypher
        rel_type = rel.relationship_type.replace("-", "_").replace(" ", "_").upper()

        cypher = f"""
        MATCH (s {{id: $source_key, workflow_id: $workflow_id}})
        MATCH (t {{id: $target_key, workflow_id: $workflow_id}})
        MERGE (s)-[r:{rel_type} {{workflow_id: $workflow_id}}]->(t)
        SET r.confidence = $confidence,
            r.evidence = $evidence,
            r.source = $source,
            r.created_at = $created_at
        RETURN r
        """

        params = {
            "source_key": source.canonical_key,
            "target_key": target.canonical_key,
            "workflow_id": str(workflow_id),
            "confidence": float(rel.confidence) if rel.confidence else 0.8,
            "evidence": [json.dumps(e) if isinstance(e, dict) else str(e) for e in (rel.attributes.get("evidence", []) if rel.attributes else [])],
            "source": "llm_extraction",
            "created_at": rel.created_at.isoformat() if hasattr(rel, 'created_at') else None
        }

        await self.neo4j_driver.execute_query(cypher, params)

    async def _create_embedding_node(
        self,
        emb: Any,
        workflow_id: str
    ) -> None:
        """Create Neo4j node for vector embedding."""

        cypher = """
        MERGE (ve:VectorEmbedding {entity_id: $entity_id, workflow_id: $workflow_id})
        SET ve.section_type = $section_type,
            ve.embedding_dim = $embedding_dim,
            ve.confidence = $confidence,
            ve.created_at = $created_at
        RETURN ve
        """

        params = {
            "entity_id": str(emb.entity_id),
            "workflow_id": str(workflow_id),
            "section_type": emb.section_type,
            "embedding_dim": emb.embedding_dim if hasattr(emb, 'embedding_dim') else 384,
            "confidence": 0.95,
            "created_at": emb.created_at.isoformat() if hasattr(emb, 'created_at') else None
        }

        await self.neo4j_driver.execute_query(cypher, params)
