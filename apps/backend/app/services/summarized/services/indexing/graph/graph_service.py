"""GraphRAG knowledge graph construction service."""

import uuid
import json
from typing import List, Dict, Any, Optional
from neo4j import AsyncDriver
from sqlalchemy.ext.asyncio import AsyncSession as SQLAlchemySession

from app.services.base_service import BaseService
from app.repositories.entity_repository import EntityRepository, EntityRelationshipRepository
from app.repositories.vector_embedding_repository import VectorEmbeddingRepository
from app.repositories.entity_evidence_repository import EntityEvidenceRepository
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
        self.evidence_repo = EntityEvidenceRepository(db_session)

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

            # Step 0: Clean up stale graph data — only when rebuilding entire workflow
            # When document_id is provided, MERGE handles idempotent upserts safely
            if not doc_uuid:
                await self._cleanup_workflow_graph(wf_uuid)

            # Step 1: Fetch entities
            if doc_uuid:
                entities_with_prov = await self.entity_repo.get_with_provenance_by_document(doc_uuid)
            else:
                entities_with_prov = await self.entity_repo.get_with_provenance_by_workflow(wf_uuid)

            LOGGER.info(f"Fetched {len(entities_with_prov)} raw entities with provenance")

            # Group provenance by entity and pick best (non-null source_section preferred)
            entity_provenance_map = {}
            for entity, source_chunk_id, source_section in entities_with_prov:
                if entity.id not in entity_provenance_map:
                    entity_provenance_map[entity.id] = (entity, source_chunk_id, source_section)
                else:
                    # Pick provenance with non-null source_section if current has null
                    _, current_chunk, current_section = entity_provenance_map[entity.id]
                    if current_section is None and source_section is not None:
                        entity_provenance_map[entity.id] = (entity, source_chunk_id, source_section)

            LOGGER.info(f"Grouped into {len(entity_provenance_map)} unique canonical entities")

            # Batch create entity nodes grouped by type for performance
            entity_count = await self._create_entity_nodes_batch(
                list(entity_provenance_map.values()), wf_uuid, doc_uuid
            )
            stats["entities_created"] = entity_count

            # Step 2: Fetch and create relationships
            if doc_uuid:
                relationships = await self.rel_repo.get_by_document(doc_uuid)
            else:
                relationships = await self.rel_repo.get_by_workflow(wf_uuid)

            # Pre-fetch all entity canonical keys in a single bulk query (avoids N+1)
            entity_ids_needed = set()
            for rel in relationships:
                if rel.source_entity_id:
                    entity_ids_needed.add(rel.source_entity_id)
                if rel.target_entity_id:
                    entity_ids_needed.add(rel.target_entity_id)
            entity_keys_map = await self.entity_repo.get_canonical_keys_by_ids(
                list(entity_ids_needed)
            ) if entity_ids_needed else {}

            # Batch create relationships grouped by signature
            rel_count = await self._create_relationships_batch(relationships, wf_uuid, entity_keys_map)
            stats["relationships_created"] = rel_count

            # Step 3: Fetch and batch create embedding nodes + HAS_EMBEDDING edges
            if doc_uuid:
                embeddings = await self.emb_repo.get_by_document(doc_uuid)
            else:
                embeddings = await self.emb_repo.get_by_workflow(wf_uuid)

            emb_count = await self._create_embeddings_batch(embeddings, wf_uuid)
            stats["embeddings_linked"] = emb_count

            # Step 4: Fetch and create evidence nodes with SUPPORTED_BY edges
            evidence_records = await self.evidence_repo.get_evidence_with_mentions_by_workflow(wf_uuid)
            stats["evidence_created"] = 0

            for evidence, mention, entity, chunk in evidence_records:
                try:
                    await self._create_evidence_node_and_edge(
                        evidence, mention, entity, chunk, wf_uuid
                    )
                    stats["evidence_created"] += 1
                except Exception as e:
                    LOGGER.error(
                        f"Failed to create evidence node: {e}",
                        extra={"evidence_id": str(evidence.id)}
                    )
                    stats["errors"] += 1

            LOGGER.info(
                "Knowledge graph construction completed",
                extra={
                    "workflow_id": str(workflow_id),
                    "stats": stats
                }
            )
            
            await self.db_session.commit()

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
        doc_uuid: Optional[uuid.UUID] = None,
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
        if doc_uuid:
            properties["document_id"] = str(doc_uuid)

        if source_chunk_id:
            properties["source_chunk_id"] = source_chunk_id
        if source_section:
            properties["source_section"] = source_section.lower()

        # Query linked vector embeddings to store their entity_ids on the node
        # This enables Cypher-only queries without PostgreSQL round-trips
        vector_entity_ids = await self._get_vector_entity_ids(entity.id)
        if vector_entity_ids:
            properties["vector_entity_ids"] = vector_entity_ids

        # Build property string for SET clause
        set_clauses = ", ".join([f"n.{key} = ${key}" for key in properties.keys()])

        cypher = f"""
        MERGE (n:{node_label} {{id: $id, workflow_id: $workflow_id}})
        SET {set_clauses}
        RETURN n
        """

        await self.neo4j_driver.execute_query(cypher, properties)

    async def _get_vector_entity_ids(self, canonical_entity_id: uuid.UUID) -> list[str]:
        """Get all vector embedding entity_ids linked to this canonical entity.

        Args:
            canonical_entity_id: UUID of the canonical entity

        Returns:
            List of vector embedding entity_id strings (e.g., ["coverages_cov_0", "coverages_cov_1"])
        """
        try:
            # Query vector embeddings that reference this canonical entity
            from sqlalchemy import select
            from app.database.models import VectorEmbedding

            query = select(VectorEmbedding.entity_id).where(
                VectorEmbedding.canonical_entity_id == canonical_entity_id
            )
            result = await self.db_session.execute(query)
            entity_ids = [row[0] for row in result.fetchall()]

            return entity_ids

        except Exception as e:
            LOGGER.warning(
                f"Failed to fetch vector entity IDs: {e}",
                extra={"canonical_entity_id": str(canonical_entity_id)}
            )
            return []

    async def _create_entity_nodes_batch(
        self,
        entities_with_prov: list[tuple],
        workflow_id: uuid.UUID,
        doc_uuid: Optional[uuid.UUID] = None
    ) -> int:
        """Batch create entity nodes grouped by type for optimal performance.

        Groups entities by entity_type and uses UNWIND for bulk insertion,
        reducing N individual queries to 1 query per entity type.

        Args:
            entities_with_prov: List of (entity, source_chunk_id, source_section) tuples
            workflow_id: Workflow UUID

        Returns:
            Total count of entities created
        """
        from collections import defaultdict

        # Group entities by type
        entities_by_type = defaultdict(list)
        for entity, source_chunk_id, source_section in entities_with_prov:
            entities_by_type[entity.entity_type].append((entity, source_chunk_id, source_section))

        LOGGER.info(f"Batching {len(entities_with_prov)} entities across {len(entities_by_type)} types")

        total_created = 0

        # Batch create per entity type
        for entity_type, entity_group in entities_by_type.items():
            try:
                # Prepare batch data
                batch_data = []
                for entity, source_chunk_id, source_section in entity_group:
                    properties = self._map_entity_properties(entity)
                    properties["id"] = entity.canonical_key
                    properties["workflow_id"] = str(workflow_id)
                    if doc_uuid:
                        properties["document_id"] = str(doc_uuid)

                    if source_chunk_id:
                        properties["source_chunk_id"] = source_chunk_id
                    if source_section:
                        properties["source_section"] = source_section.lower()

                    # Get vector entity IDs
                    vector_entity_ids = await self._get_vector_entity_ids(entity.id)
                    if vector_entity_ids:
                        properties["vector_entity_ids"] = vector_entity_ids

                    batch_data.append(properties)

                # Build UNWIND Cypher query
                cypher = f"""
                UNWIND $batch AS item
                MERGE (n:{entity_type} {{id: item.id, workflow_id: item.workflow_id}})
                SET n += item
                RETURN count(n) as created_count
                """

                result = await self.neo4j_driver.execute_query(cypher, {"batch": batch_data})
                # Extract count from result
                records = result.records if hasattr(result, 'records') else []
                created_count = records[0]["created_count"] if records else len(batch_data)
                total_created += created_count

                LOGGER.debug(
                    f"Batch created {created_count} {entity_type} nodes",
                    extra={"entity_type": entity_type, "count": created_count}
                )

            except Exception as e:
                LOGGER.error(
                    f"Failed to batch create {entity_type} nodes: {e}",
                    extra={"entity_type": entity_type}
                )
                # Fallback to individual creation if batch fails
                for entity, source_chunk_id, source_section in entity_group:
                    try:
                        await self._create_entity_node(entity, workflow_id, doc_uuid, source_chunk_id, source_section)
                        total_created += 1
                    except Exception as e2:
                        LOGGER.error(f"Failed to create entity node: {e2}", extra={"entity_id": str(entity.id)})

        return total_created

    def _map_entity_properties(self, entity: Any) -> Dict[str, Any]:
        """Map entity attributes to schema-defined properties."""
        
        attrs = entity.attributes or {}
        entity_type = entity.entity_type
        
        # Derive a human-readable name from attributes with fallback
        # Different entity types store their name under different keys
        display_name = (
            attrs.get("name")
            or attrs.get("title")
            or attrs.get("coverage_name")
            or attrs.get("exclusion_name")
            or attrs.get("term")
            or attrs.get("coverage_type")
            or attrs.get("policy_number")
            or attrs.get("claim_number")
            or attrs.get("endorsement_number")
            or entity.canonical_key  # last resort: use the hash key
        )

        # FIX 1 VERIFICATION: Log when coverage_name/exclusion_name is used for display_name
        if entity_type == "Coverage" and attrs.get("coverage_name"):
            LOGGER.debug(
                f"Coverage display_name resolved from coverage_name",
                extra={
                    "canonical_key": entity.canonical_key,
                    "coverage_name": attrs.get("coverage_name"),
                    "coverage_type": attrs.get("coverage_type"),
                    "display_name": display_name
                }
            )
        elif entity_type == "Exclusion" and attrs.get("exclusion_name"):
            LOGGER.debug(
                f"Exclusion display_name resolved from exclusion_name",
                extra={
                    "canonical_key": entity.canonical_key,
                    "exclusion_name": attrs.get("exclusion_name"),
                    "display_name": display_name
                }
            )
        
        # Base properties — always set entity_type and name so nodes
        # are identifiable during traversal and context assembly
        props = {
            "id": entity.canonical_key,
            "entity_type": entity_type,
            "name": display_name,
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
            coverage_name_prop = attrs.get("name") or attrs.get("coverage_name") or display_name
            props.update({
                "name": coverage_name_prop,
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

            # FIX 1 VERIFICATION: Log Coverage node properties including description
            LOGGER.debug(
                f"Coverage node properties mapped",
                extra={
                    "canonical_key": entity.canonical_key,
                    "node_name": coverage_name_prop,
                    "coverage_type": attrs.get("coverage_type"),
                    "has_description": bool(attrs.get("description")),
                    "description_length": len(attrs.get("description", ""))
                }
            )

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

        elif entity_type == "Exclusion":
            props.update({
                "name": attrs.get("name") or attrs.get("title"),
                "exclusion_type": attrs.get("exclusion_type") or attrs.get("type"),
                "description": attrs.get("description"),
                "applies_to": attrs.get("applies_to"),
                "source_text": attrs.get("source_text"),
            })

        elif entity_type == "Definition":
            props.update({
                "term": attrs.get("term"),
                "definition_text": attrs.get("definition_text") or attrs.get("definition"),
            })

        elif entity_type == "Monetary":
            props.update({
                "amount": attrs.get("amount"),
                "currency": attrs.get("currency"),
                "description": attrs.get("description"),
                "monetary_type": attrs.get("type"),
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
        workflow_id: uuid.UUID,
        entity_keys_map: Dict[uuid.UUID, tuple] = None
    ) -> None:
        """Create Neo4j edge for relationship.

        Args:
            rel: EntityRelationship record.
            workflow_id: Workflow UUID.
            entity_keys_map: Pre-fetched mapping of entity UUID -> (canonical_key, entity_type).
                             If None, falls back to individual DB lookups.
        """
        # Resolve source and target canonical keys + entity types
        if entity_keys_map and rel.source_entity_id in entity_keys_map and rel.target_entity_id in entity_keys_map:
            source_key, source_type = entity_keys_map[rel.source_entity_id]
            target_key, target_type = entity_keys_map[rel.target_entity_id]
        else:
            # Fallback to individual lookups (backward compat)
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
            source_key, source_type = source.canonical_key, source.entity_type
            target_key, target_type = target.canonical_key, target.entity_type

        # Sanitize relationship type for Cypher
        rel_type = rel.relationship_type.replace("-", "_").replace(" ", "_").upper()

        # Extract provenance metadata from relationship
        document_id = str(rel.document_id) if hasattr(rel, 'document_id') and rel.document_id else None
        section_type = rel.attributes.get("section_type") if rel.attributes else None

        # Use labeled MATCH for index-backed lookups instead of full graph scan
        cypher = f"""
        MATCH (s:{source_type} {{id: $source_key, workflow_id: $workflow_id}})
        MATCH (t:{target_type} {{id: $target_key, workflow_id: $workflow_id}})
        MERGE (s)-[r:{rel_type} {{workflow_id: $workflow_id}}]->(t)
        SET r.confidence = $confidence,
            r.evidence = $evidence,
            r.source = $source,
            r.document_id = $document_id,
            r.section_type = $section_type,
            r.created_at = $created_at
        RETURN r
        """

        params = {
            "source_key": source_key,
            "target_key": target_key,
            "workflow_id": str(workflow_id),
            "confidence": float(rel.confidence) if rel.confidence else 0.8,
            "evidence": [json.dumps(e) if isinstance(e, dict) else str(e) for e in (rel.attributes.get("evidence", []) if rel.attributes else [])],
            "source": "llm_extraction",
            "document_id": document_id,
            "section_type": section_type,
            "created_at": rel.created_at.isoformat() if hasattr(rel, 'created_at') else None
        }

        await self.neo4j_driver.execute_query(cypher, params)

    async def _create_relationships_batch(
        self,
        relationships: list,
        workflow_id: uuid.UUID,
        entity_keys_map: Dict[uuid.UUID, tuple]
    ) -> int:
        """Batch create relationship edges grouped by signature for optimal performance.

        Groups relationships by (source_type, target_type, rel_type) and uses UNWIND,
        reducing N individual queries to 1 query per relationship signature.

        Args:
            relationships: List of EntityRelationship records
            workflow_id: Workflow UUID
            entity_keys_map: Pre-fetched entity canonical keys

        Returns:
            Total count of relationships created
        """
        from collections import defaultdict

        # Group relationships by signature (source_type, target_type, rel_type)
        rels_by_signature = defaultdict(list)

        for rel in relationships:
            # Resolve entity keys
            if rel.source_entity_id not in entity_keys_map or rel.target_entity_id not in entity_keys_map:
                LOGGER.warning(
                    "Skipping relationship with missing entities",
                    extra={
                        "source_id": str(rel.source_entity_id),
                        "target_id": str(rel.target_entity_id)
                    }
                )
                continue

            source_key, source_type = entity_keys_map[rel.source_entity_id]
            target_key, target_type = entity_keys_map[rel.target_entity_id]
            rel_type = rel.relationship_type.replace("-", "_").replace(" ", "_").upper()

            signature = (source_type, target_type, rel_type)
            rels_by_signature[signature].append((rel, source_key, target_key))

        LOGGER.info(f"Grouped {len(relationships)} relationships into {len(rels_by_signature)} signatures")
        for sig, group in rels_by_signature.items():
            LOGGER.info(f"  Signature {sig}: {len(group)} relationships")

        total_created = 0

        # Batch create per signature
        for (source_type, target_type, rel_type), rel_group in rels_by_signature.items():
            try:
                # Prepare batch data
                batch_data = []
                for rel, source_key, target_key in rel_group:
                    document_id = str(rel.document_id) if hasattr(rel, 'document_id') and rel.document_id else None
                    section_type = rel.attributes.get("section_type") if rel.attributes else None

                    batch_data.append({
                        "source_key": source_key,
                        "target_key": target_key,
                        "workflow_id": str(workflow_id),
                        "confidence": float(rel.confidence) if rel.confidence else 0.8,
                        "evidence": [json.dumps(e) if isinstance(e, dict) else str(e) for e in (rel.attributes.get("evidence", []) if rel.attributes else [])],
                        "source": "llm_extraction",
                        "document_id": document_id,
                        "section_type": section_type,
                        "created_at": rel.created_at.isoformat() if hasattr(rel, 'created_at') else None
                    })

                # Build UNWIND Cypher query
                cypher = f"""
                UNWIND $batch AS item
                MATCH (s:{source_type} {{id: item.source_key, workflow_id: item.workflow_id}})
                MATCH (t:{target_type} {{id: item.target_key, workflow_id: item.workflow_id}})
                MERGE (s)-[r:{rel_type} {{workflow_id: item.workflow_id}}]->(t)
                SET r.confidence = item.confidence,
                    r.evidence = item.evidence,
                    r.source = item.source,
                    r.document_id = item.document_id,
                    r.section_type = item.section_type,
                    r.created_at = item.created_at
                RETURN count(r) as created_count
                """

                result = await self.neo4j_driver.execute_query(cypher, {"batch": batch_data})
                records = result.records if hasattr(result, 'records') else []
                created_count = records[0]["created_count"] if records else len(batch_data)
                total_created += created_count

                LOGGER.debug(
                    f"Batch created {created_count} {rel_type} relationships",
                    extra={"signature": f"{source_type}->{target_type}", "count": created_count}
                )

            except Exception as e:
                LOGGER.error(
                    f"Failed to batch create {rel_type} relationships: {e}",
                    extra={"signature": f"{source_type}->{target_type}"}
                )
                # Fallback to individual creation if batch fails
                for rel, _, _ in rel_group:
                    try:
                        await self._create_relationship_edge(rel, workflow_id, entity_keys_map)
                        total_created += 1
                    except Exception as e2:
                        LOGGER.error(f"Failed to create relationship: {e2}", extra={"rel_id": str(rel.id)})

        return total_created

    async def _cleanup_workflow_graph(self, workflow_id: uuid.UUID) -> None:
        """Remove all nodes and edges for a workflow before reconstruction.

        Iterates over known node labels so each DELETE can leverage per-label
        workflow_id indexes instead of a full graph scan.
        """
        from app.core.neo4j_client import Neo4jClientManager

        wf_str = str(workflow_id)
        all_labels = Neo4jClientManager.ENTITY_LABELS + ["VectorEmbedding", "Evidence"]
        for label in all_labels:
            cypher = f"MATCH (n:{label} {{workflow_id: $workflow_id}}) DETACH DELETE n"
            await self.neo4j_driver.execute_query(
                cypher, {"workflow_id": wf_str}
            )
        LOGGER.info(
            "Cleaned up existing graph data for workflow",
            extra={"workflow_id": wf_str}
        )

    async def _create_embedding_node(
        self,
        emb: Any,
        workflow_id: uuid.UUID
    ) -> None:
        """Create Neo4j node for vector embedding and HAS_EMBEDDING edge if canonical entity exists."""

        # Normalize entity_type to title-case for consistency with CanonicalEntity
        entity_type_normalized = emb.entity_type.title() if hasattr(emb, 'entity_type') and emb.entity_type else None

        # Create VectorEmbedding node
        cypher = """
        MERGE (ve:VectorEmbedding {entity_id: $entity_id, workflow_id: $workflow_id})
        SET ve.section_type = $section_type,
            ve.entity_type = $entity_type,
            ve.embedding_dim = $embedding_dim,
            ve.confidence = $confidence,
            ve.created_at = $created_at
        RETURN ve
        """

        params = {
            "entity_id": str(emb.entity_id),
            "workflow_id": str(workflow_id),
            "section_type": emb.section_type,
            "entity_type": entity_type_normalized,
            "embedding_dim": emb.embedding_dim if hasattr(emb, 'embedding_dim') else 384,
            "confidence": 0.95,
            "created_at": emb.created_at.isoformat() if hasattr(emb, 'created_at') else None
        }

        await self.neo4j_driver.execute_query(cypher, params)

        # Create HAS_EMBEDDING edge if canonical entity is linked
        if hasattr(emb, 'canonical_entity_id') and emb.canonical_entity_id:
            await self._create_has_embedding_edge(emb, workflow_id)

    async def _create_has_embedding_edge(
        self,
        emb: Any,
        workflow_id: uuid.UUID
    ) -> None:
        """Create HAS_EMBEDDING edge from entity to embedding node.

        Args:
            emb: VectorEmbedding record with canonical_entity_id populated
            workflow_id: Workflow UUID
        """
        try:
            # Fetch the canonical entity to get its canonical_key and entity_type
            canonical_entity = await self.entity_repo.get_by_id(emb.canonical_entity_id)

            if not canonical_entity:
                LOGGER.warning(
                    "Canonical entity not found for embedding",
                    extra={
                        "canonical_entity_id": str(emb.canonical_entity_id),
                        "embedding_entity_id": str(emb.entity_id)
                    }
                )
                return

            # Use labeled MATCH for both nodes, create HAS_EMBEDDING edge
            entity_type = canonical_entity.entity_type
            cypher = f"""
            MATCH (e:{entity_type} {{id: $canonical_key, workflow_id: $workflow_id}})
            MATCH (ve:VectorEmbedding {{entity_id: $entity_id, workflow_id: $workflow_id}})
            MERGE (e)-[r:HAS_EMBEDDING]->(ve)
            RETURN r
            """

            params = {
                "canonical_key": canonical_entity.canonical_key,
                "entity_id": str(emb.entity_id),
                "workflow_id": str(workflow_id)
            }

            await self.neo4j_driver.execute_query(cypher, params)

            LOGGER.debug(
                "Created HAS_EMBEDDING edge",
                extra={
                    "entity_type": entity_type,
                    "canonical_key": canonical_entity.canonical_key,
                    "embedding_entity_id": str(emb.entity_id)
                }
            )

        except Exception as e:
            LOGGER.error(
                f"Failed to create HAS_EMBEDDING edge: {e}",
                extra={
                    "embedding_id": str(emb.id),
                    "canonical_entity_id": str(emb.canonical_entity_id) if hasattr(emb, 'canonical_entity_id') else None
                }
            )

    async def _create_embeddings_batch(
        self,
        embeddings: list,
        workflow_id: uuid.UUID
    ) -> int:
        """Batch create embedding nodes and HAS_EMBEDDING edges for optimal performance.

        Creates VectorEmbedding nodes in bulk, then creates HAS_EMBEDDING edges
        for those linked to canonical entities.

        Args:
            embeddings: List of VectorEmbedding records
            workflow_id: Workflow UUID

        Returns:
            Total count of embeddings created
        """
        if not embeddings:
            return 0

        # Prepare batch data for VectorEmbedding nodes
        batch_data = []
        linked_embeddings = []  # Track embeddings with canonical_entity_id for edge creation

        for emb in embeddings:
            entity_type_normalized = emb.entity_type.title() if hasattr(emb, 'entity_type') and emb.entity_type else None

            batch_data.append({
                "entity_id": str(emb.entity_id),
                "workflow_id": str(workflow_id),
                "section_type": emb.section_type,
                "entity_type": entity_type_normalized,
                "embedding_dim": emb.embedding_dim if hasattr(emb, 'embedding_dim') else 384,
                "confidence": 0.95,
                "created_at": emb.created_at.isoformat() if hasattr(emb, 'created_at') else None
            })

            # Track embeddings with canonical entity for edge creation
            if hasattr(emb, 'canonical_entity_id') and emb.canonical_entity_id:
                linked_embeddings.append(emb)

        try:
            # Batch create VectorEmbedding nodes
            cypher = """
            UNWIND $batch AS item
            MERGE (ve:VectorEmbedding {entity_id: item.entity_id, workflow_id: item.workflow_id})
            SET ve.section_type = item.section_type,
                ve.entity_type = item.entity_type,
                ve.embedding_dim = item.embedding_dim,
                ve.confidence = item.confidence,
                ve.created_at = item.created_at
            RETURN count(ve) as created_count
            """

            result = await self.neo4j_driver.execute_query(cypher, {"batch": batch_data})
            records = result.records if hasattr(result, 'records') else []
            created_count = records[0]["created_count"] if records else len(batch_data)

            LOGGER.debug(
                f"Batch created {created_count} VectorEmbedding nodes",
                extra={"count": created_count}
            )

            # Create HAS_EMBEDDING edges for linked embeddings
            if linked_embeddings:
                await self._create_has_embedding_edges_batch(linked_embeddings, workflow_id)

            return created_count

        except Exception as e:
            LOGGER.error(f"Failed to batch create embeddings: {e}")
            # Fallback to individual creation
            count = 0
            for emb in embeddings:
                try:
                    await self._create_embedding_node(emb, workflow_id)
                    count += 1
                except Exception as e2:
                    LOGGER.error(f"Failed to create embedding: {e2}", extra={"emb_id": str(emb.id)})
            return count

    async def _create_has_embedding_edges_batch(
        self,
        embeddings: list,
        workflow_id: uuid.UUID
    ) -> None:
        """Batch create HAS_EMBEDDING edges for embeddings linked to canonical entities.

        Args:
            embeddings: List of VectorEmbedding records with canonical_entity_id
            workflow_id: Workflow UUID
        """
        from collections import defaultdict

        # Pre-fetch all canonical entities
        entity_ids = [emb.canonical_entity_id for emb in embeddings if hasattr(emb, 'canonical_entity_id')]
        if not entity_ids:
            return

        # Fetch entities in bulk
        entities = {}
        for entity_id in entity_ids:
            entity = await self.entity_repo.get_by_id(entity_id)
            if entity:
                entities[entity_id] = entity

        # Group embeddings by entity type for batch edge creation
        edges_by_type = defaultdict(list)
        for emb in embeddings:
            if not hasattr(emb, 'canonical_entity_id') or not emb.canonical_entity_id:
                continue

            entity = entities.get(emb.canonical_entity_id)
            if not entity:
                continue

            edges_by_type[entity.entity_type].append({
                "canonical_key": entity.canonical_key,
                "entity_id": str(emb.entity_id),
                "workflow_id": str(workflow_id)
            })

        # Batch create edges per entity type
        for entity_type, edge_batch in edges_by_type.items():
            try:
                cypher = f"""
                UNWIND $batch AS item
                MATCH (e:{entity_type} {{id: item.canonical_key, workflow_id: item.workflow_id}})
                MATCH (ve:VectorEmbedding {{entity_id: item.entity_id, workflow_id: item.workflow_id}})
                MERGE (e)-[r:HAS_EMBEDDING]->(ve)
                RETURN count(r) as created_count
                """

                result = await self.neo4j_driver.execute_query(cypher, {"batch": edge_batch})
                records = result.records if hasattr(result, 'records') else []
                created_count = records[0]["created_count"] if records else len(edge_batch)

                LOGGER.debug(
                    f"Batch created {created_count} HAS_EMBEDDING edges for {entity_type}",
                    extra={"entity_type": entity_type, "count": created_count}
                )

            except Exception as e:
                LOGGER.error(
                    f"Failed to batch create HAS_EMBEDDING edges for {entity_type}: {e}",
                    extra={"entity_type": entity_type}
                )

    async def _create_evidence_node_and_edge(
        self,
        evidence: Any,
        mention: Any,
        entity: Any,
        chunk: Any,
        workflow_id: uuid.UUID
    ) -> None:
        """Create Evidence node and SUPPORTED_BY edge for explainable GraphRAG.

        Evidence nodes capture the raw text evidence that supports an entity extraction,
        enabling citation and explainability in RAG responses.

        Args:
            evidence: EntityEvidence record
            mention: EntityMention record with source text
            entity: CanonicalEntity record
            chunk: StableChunk record (may be None)
            workflow_id: Workflow UUID
        """
        # Extract evidence properties
        evidence_id = f"evidence_{str(evidence.id)[:8]}"
        document_id = str(evidence.document_id)
        chunk_id = str(mention.source_stable_chunk_id) if mention.source_stable_chunk_id else None

        # Get source text (quote) from mention
        quote = mention.mention_text if hasattr(mention, 'mention_text') and mention.mention_text else ""
        if not quote and chunk:
            # Fallback to chunk text if mention text not available
            quote = chunk.text[:500] if hasattr(chunk, 'text') and chunk.text else ""

        # Get page number from chunk metadata if available
        page_number = None
        if chunk and hasattr(chunk, 'metadata') and chunk.metadata:
            page_number = chunk.metadata.get('page_number')

        # Create Evidence node
        evidence_cypher = """
        MERGE (ev:Evidence {id: $evidence_id, workflow_id: $workflow_id})
        SET ev.document_id = $document_id,
            ev.chunk_id = $chunk_id,
            ev.quote = $quote,
            ev.page_number = $page_number,
            ev.confidence = $confidence,
            ev.evidence_type = $evidence_type,
            ev.created_at = $created_at
        RETURN ev
        """

        evidence_params = {
            "evidence_id": evidence_id,
            "workflow_id": str(workflow_id),
            "document_id": document_id,
            "chunk_id": chunk_id,
            "quote": quote,
            "page_number": page_number,
            "confidence": float(evidence.confidence) if evidence.confidence else 0.9,
            "evidence_type": evidence.evidence_type if hasattr(evidence, 'evidence_type') else "extracted",
            "created_at": evidence.created_at.isoformat() if hasattr(evidence, 'created_at') else None
        }

        await self.neo4j_driver.execute_query(evidence_cypher, evidence_params)

        # Create SUPPORTED_BY edge from entity to evidence
        entity_type = entity.entity_type
        edge_cypher = f"""
        MATCH (e:{entity_type} {{id: $canonical_key, workflow_id: $workflow_id}})
        MATCH (ev:Evidence {{id: $evidence_id, workflow_id: $workflow_id}})
        MERGE (e)-[r:SUPPORTED_BY]->(ev)
        RETURN r
        """

        edge_params = {
            "canonical_key": entity.canonical_key,
            "evidence_id": evidence_id,
            "workflow_id": str(workflow_id)
        }

        await self.neo4j_driver.execute_query(edge_cypher, edge_params)

        LOGGER.debug(
            "Created Evidence node and SUPPORTED_BY edge",
            extra={
                "evidence_id": evidence_id,
                "entity_type": entity_type,
                "canonical_key": entity.canonical_key
            }
        )
