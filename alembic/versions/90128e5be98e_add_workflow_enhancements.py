"""add_workflow_enhancements

Revision ID: 90128e5be98e
Revises: 02652959ea7e
Create Date: 2026-01-04 18:06:41.845027

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '90128e5be98e'
down_revision: Union[str, Sequence[str], None] = '02652959ea7e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # workflow_definitions
    op.create_table('workflow_definitions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workflow_key', sa.String(), nullable=False),
    sa.Column('display_name', sa.String(), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('supports_multi_docs', sa.Boolean(), nullable=False, server_default='false'),
    sa.Column('supported_steps', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default='NOW()', nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('workflow_key')
    )

    # workflow_documents
    op.create_table('workflow_documents',
    sa.Column('workflow_id', sa.UUID(), nullable=False),
    sa.Column('document_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default='NOW()', nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workflow_id'], ['workflows.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('workflow_id', 'document_id')
    )

    # workflow_stage_runs
    op.create_table('workflow_stage_runs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workflow_id', sa.UUID(), nullable=False),
    sa.Column('stage_name', sa.String(), nullable=False),
    sa.Column('status', sa.String(), nullable=False, server_default='pending'),
    sa.Column('started_at', sa.TIMESTAMP(timezone=True), nullable=True),
    sa.Column('completed_at', sa.TIMESTAMP(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['workflow_id'], ['workflows.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )

    # workflow_entity_scope
    op.create_table('workflow_entity_scope',
    sa.Column('workflow_id', sa.UUID(), nullable=False),
    sa.Column('canonical_entity_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['canonical_entity_id'], ['canonical_entities.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workflow_id'], ['workflows.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('workflow_id', 'canonical_entity_id')
    )

    # workflow_relationship_scope
    op.create_table('workflow_relationship_scope',
    sa.Column('workflow_id', sa.UUID(), nullable=False),
    sa.Column('relationship_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['relationship_id'], ['entity_relationships.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workflow_id'], ['workflows.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('workflow_id', 'relationship_id')
    )

    # workflows modifications
    op.add_column('workflows', sa.Column('workflow_definition_id', sa.UUID(), nullable=True))
    op.create_foreign_key('fk_workflows_definition_id', 'workflows', 'workflow_definitions', ['workflow_definition_id'], ['id'])

    # entity_relationships modifications
    op.add_column('entity_relationships', sa.Column('document_id', sa.UUID(), nullable=True))
    op.create_foreign_key('fk_entity_relationships_document_id', 'entity_relationships', 'documents', ['document_id'], ['id'], ondelete='CASCADE')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_entity_relationships_document_id', 'entity_relationships', type_='foreignkey')
    op.drop_column('entity_relationships', 'document_id')
    op.drop_constraint('fk_workflows_definition_id', 'workflows', type_='foreignkey')
    op.drop_column('workflows', 'workflow_definition_id')
    op.drop_table('workflow_relationship_scope')
    op.drop_table('workflow_entity_scope')
    op.drop_table('workflow_stage_runs')
    op.drop_table('workflow_documents')
    op.drop_table('workflow_definitions')
