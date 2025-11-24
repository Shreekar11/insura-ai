"""add_content_hash_and_provenance_tracking

Revision ID: 44c04852b488
Revises: f2688e902562
Create Date: 2025-11-24 09:26:53.448990

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '44c04852b488'
down_revision: Union[str, Sequence[str], None] = 'f2688e902562'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add content_hash and provenance tracking columns to normalized_chunks
    op.add_column('normalized_chunks', sa.Column('content_hash', sa.String(length=64), nullable=True, comment='SHA256 hash of normalized_text for change detection'))
    op.add_column('normalized_chunks', sa.Column('prompt_version', sa.String(), nullable=True, comment='Prompt template version used'))
    op.add_column('normalized_chunks', sa.Column('pipeline_run_id', sa.String(), nullable=True, comment='Pipeline execution identifier'))
    op.add_column('normalized_chunks', sa.Column('source_stage', sa.String(), nullable=True, comment='Pipeline stage that created this'))
    op.add_column('normalized_chunks', sa.Column('extracted_at', sa.TIMESTAMP(timezone=True), nullable=True, comment='When extraction was performed'))
    
    # Create indexes for performance
    op.create_index('ix_normalized_chunks_content_hash', 'normalized_chunks', ['content_hash'])
    op.create_index('ix_normalized_chunks_pipeline_run_id', 'normalized_chunks', ['pipeline_run_id'])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes
    op.drop_index('ix_normalized_chunks_pipeline_run_id', table_name='normalized_chunks')
    op.drop_index('ix_normalized_chunks_content_hash', table_name='normalized_chunks')
    
    # Drop columns
    op.drop_column('normalized_chunks', 'extracted_at')
    op.drop_column('normalized_chunks', 'source_stage')
    op.drop_column('normalized_chunks', 'pipeline_run_id')
    op.drop_column('normalized_chunks', 'prompt_version')
    op.drop_column('normalized_chunks', 'content_hash')
