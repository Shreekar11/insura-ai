"""Add document_tables for TableJSON storage.

Revision ID: c3d4e5f6g7h8
Revises: 2c713aae6b0d
Create Date: 2024-12-26

This migration adds the document_tables table for storing
first-class table representations with full structural information.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'c3d4e5f6g7h8'
down_revision = '2c713aae6b0d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create document_tables table."""
    op.create_table(
        'document_tables',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), 
                  sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('page_number', sa.Integer(), nullable=False, 
                  comment='1-indexed page number'),
        sa.Column('table_index', sa.Integer(), nullable=False, default=0,
                  comment='0-indexed table position on page'),
        sa.Column('stable_table_id', sa.String(), unique=True, nullable=False,
                  comment='Deterministic ID: tbl_{doc_id}_p{page}_t{index}'),
        
        # Table structure as JSON
        sa.Column('table_json', postgresql.JSONB(), nullable=False,
                  comment='Full TableJSON with cells, headers, spans, bboxes'),
        
        # Bounding box
        sa.Column('table_bbox', postgresql.JSONB(), nullable=True,
                  comment='[x1, y1, x2, y2] coordinates on page'),
        
        # Structure metrics
        sa.Column('num_rows', sa.Integer(), nullable=False, default=0,
                  comment='Total row count'),
        sa.Column('num_cols', sa.Integer(), nullable=False, default=0,
                  comment='Total column count'),
        sa.Column('header_rows', postgresql.JSONB(), nullable=False,
                  server_default='[]', comment='Indices of header rows'),
        sa.Column('canonical_headers', postgresql.JSONB(), nullable=False,
                  server_default='[]', comment='Reconstructed header strings'),
        
        # Classification
        sa.Column('table_type', sa.String(), nullable=True,
                  comment='property_sov, loss_run, premium_schedule, etc.'),
        sa.Column('classification_confidence', sa.Numeric(5, 4), nullable=True,
                  comment='Classification confidence (0.0-1.0)'),
        sa.Column('classification_reasoning', sa.Text(), nullable=True,
                  comment='Human-readable classification reasoning'),
        
        # Extraction provenance
        sa.Column('extraction_source', sa.String(), nullable=False,
                  server_default='docling_structural',
                  comment='docling_structural, docling_markdown, camelot, tabula, etc.'),
        sa.Column('extractor_version', sa.String(), nullable=False,
                  server_default='1.0.0', comment='Version of extractor'),
        
        # Confidence metrics
        sa.Column('confidence_overall', sa.Numeric(5, 4), nullable=True,
                  comment='Overall extraction confidence'),
        sa.Column('confidence_metrics', postgresql.JSONB(), nullable=True,
                  comment='Detailed confidence metrics'),
        
        # Raw data
        sa.Column('raw_markdown', sa.Text(), nullable=True,
                  comment='Original markdown representation'),
        sa.Column('notes', sa.Text(), nullable=True,
                  comment='Footer/footnote text'),
        
        # Metadata
        sa.Column('additional_metadata', postgresql.JSONB(), nullable=True,
                  comment='Additional extraction metadata'),
        
        # Timestamps
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), 
                  server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True),
                  server_default=sa.text('NOW()'), nullable=False),
        
        # Constraints
        sa.UniqueConstraint('document_id', 'page_number', 'table_index',
                           name='uq_document_table_position'),
        
        comment='First-class table storage with full structural information'
    )
    
    # Create indexes for common queries
    op.create_index(
        'ix_document_tables_document_id',
        'document_tables',
        ['document_id']
    )
    op.create_index(
        'ix_document_tables_table_type',
        'document_tables',
        ['table_type']
    )
    op.create_index(
        'ix_document_tables_page_number',
        'document_tables',
        ['document_id', 'page_number']
    )


def downgrade() -> None:
    """Drop document_tables table."""
    op.drop_index('ix_document_tables_page_number', table_name='document_tables')
    op.drop_index('ix_document_tables_table_type', table_name='document_tables')
    op.drop_index('ix_document_tables_document_id', table_name='document_tables')
    op.drop_table('document_tables')

