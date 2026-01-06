"""add step output tables

Revision ID: 02652959ea7e
Revises: h8i9j0k1l2m3
Create Date: 2026-01-04 00:07:58.544571

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '02652959ea7e'
down_revision: Union[str, Sequence[str], None] = 'f2688e902562'
revision = '02652959ea7e'
down_revision = 'h8i9j0k1l2m3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('step_entity_outputs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('document_id', sa.UUID(), nullable=False),
    sa.Column('workflow_id', sa.UUID(), nullable=False),
    sa.Column('entity_type', sa.String(), nullable=False, comment='Entity type: Insured, Carrier, etc.'),
    sa.Column('entity_label', sa.String(), nullable=False, comment='Display label for the entity'),
    sa.Column('display_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False, comment='Normalized display payload'),
    sa.Column('confidence', sa.Numeric(precision=5, scale=4), nullable=True, comment='Overall confidence (0.0-1.0)'),
    sa.Column('source_section_extraction_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default='NOW()', nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['source_section_extraction_id'], ['section_extractions.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workflow_id'], ['workflows.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    comment='Step-scoped entity level outputs'
    )
    op.create_table('step_section_outputs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('document_id', sa.UUID(), nullable=False),
    sa.Column('workflow_id', sa.UUID(), nullable=False),
    sa.Column('section_type', sa.String(), nullable=False, comment='Section type: Declarations, Coverages, etc.'),
    sa.Column('display_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False, comment='Normalized display payload'),
    sa.Column('confidence', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Confidence metrics'),
    sa.Column('page_range', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Page range: {start: int, end: int}'),
    sa.Column('source_section_extraction_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default='NOW()', nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['source_section_extraction_id'], ['section_extractions.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workflow_id'], ['workflows.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    comment='Step-scoped section level outputs'
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('step_section_outputs')
    op.drop_table('step_entity_outputs')
