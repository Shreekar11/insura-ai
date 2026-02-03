"""add citations table and page dimensions

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2026-02-03 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6g7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create citations table for source mapping
    op.create_table(
        'citations',
        sa.Column('id', sa.UUID(), nullable=False, default=sa.text('gen_random_uuid()')),
        sa.Column('document_id', sa.UUID(), nullable=False),
        sa.Column('source_type', sa.String(length=50), nullable=False,
                  comment='Type: effective_coverage, effective_exclusion, endorsement, condition'),
        sa.Column('source_id', sa.String(length=255), nullable=False,
                  comment='Canonical ID or stable ID of the source item'),
        sa.Column('spans', postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  comment='Array of span objects: [{page_number, bounding_boxes, text_content}]'),
        sa.Column('verbatim_text', sa.Text(), nullable=False,
                  comment='Exact extracted policy language'),
        sa.Column('primary_page', sa.Integer(), nullable=False,
                  comment='Primary page number (1-indexed) for initial navigation'),
        sa.Column('page_range', postgresql.JSONB(astext_type=sa.Text()), nullable=True,
                  comment='Page range: {start: int, end: int} for multi-page citations'),
        sa.Column('extraction_confidence', sa.Numeric(precision=5, scale=4), nullable=True,
                  comment='Confidence in source mapping accuracy (0.0-1.0)'),
        sa.Column('extraction_method', sa.String(length=50), nullable=False, server_default='docling',
                  comment='Method: docling, pdfplumber, manual'),
        sa.Column('clause_reference', sa.String(length=255), nullable=True,
                  comment='Clause reference e.g., SECTION II.B.3 or Endorsement CA 20 48'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('document_id', 'source_type', 'source_id', name='uq_citation_source'),
        comment='Citation source mapping for extracted items'
    )

    # Create indexes for efficient lookup
    op.create_index('ix_citations_document_id', 'citations', ['document_id'])
    op.create_index('ix_citations_source_type', 'citations', ['source_type'])
    op.create_index('ix_citations_primary_page', 'citations', ['primary_page'])

    # Add page dimension columns to document_pages for coordinate transformation
    op.add_column(
        'document_pages',
        sa.Column(
            'width_points',
            sa.Numeric(precision=10, scale=4),
            nullable=True,
            comment='Page width in PDF points (1 point = 1/72 inch)'
        )
    )
    op.add_column(
        'document_pages',
        sa.Column(
            'height_points',
            sa.Numeric(precision=10, scale=4),
            nullable=True,
            comment='Page height in PDF points'
        )
    )
    op.add_column(
        'document_pages',
        sa.Column(
            'rotation',
            sa.Integer(),
            nullable=True,
            server_default='0',
            comment='Page rotation in degrees (0, 90, 180, 270)'
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Remove page dimension columns from document_pages
    op.drop_column('document_pages', 'rotation')
    op.drop_column('document_pages', 'height_points')
    op.drop_column('document_pages', 'width_points')

    # Drop indexes
    op.drop_index('ix_citations_primary_page', table_name='citations')
    op.drop_index('ix_citations_source_type', table_name='citations')
    op.drop_index('ix_citations_document_id', table_name='citations')

    # Drop citations table
    op.drop_table('citations')
