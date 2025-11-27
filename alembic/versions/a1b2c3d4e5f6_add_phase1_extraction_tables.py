"""Add Phase 1 extraction tables and update existing tables

Revision ID: a1b2c3d4e5f6
Revises: 44c04852b488
Create Date: 2025-11-24 19:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '44c04852b488'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    
    # Add chunk_id to existing sov_items table
    op.add_column('sov_items', sa.Column('chunk_id', sa.UUID(), nullable=True))
    op.create_foreign_key('fk_sov_items_chunk_id', 'sov_items', 'document_chunks', ['chunk_id'], ['id'])
    
    # Add missing fields to sov_items
    op.add_column('sov_items', sa.Column('address', sa.Text(), nullable=True, comment='Property address'))
    op.add_column('sov_items', sa.Column('building_limit', sa.Numeric(), nullable=True, comment='Building coverage limit'))
    op.add_column('sov_items', sa.Column('contents_limit', sa.Numeric(), nullable=True, comment='Contents coverage limit'))
    op.add_column('sov_items', sa.Column('bi_limit', sa.Numeric(), nullable=True, comment='Business interruption limit'))
    op.add_column('sov_items', sa.Column('total_insured_value', sa.Numeric(), nullable=True, comment='Total insured value (TIV)'))
    
    # Remove old columns from sov_items if they exist
    # Note: These will be replaced by the new columns above
    try:
        op.drop_column('sov_items', 'limit')
        op.drop_column('sov_items', 'deductible')
    except:
        pass  # Columns might not exist in all environments
    
    # Add chunk_id and missing fields to existing loss_run_claims table
    op.add_column('loss_run_claims', sa.Column('chunk_id', sa.UUID(), nullable=True))
    op.create_foreign_key('fk_loss_run_claims_chunk_id', 'loss_run_claims', 'document_chunks', ['chunk_id'], ['id'])
    
    op.add_column('loss_run_claims', sa.Column('policy_number', sa.String(), nullable=True, comment='Associated policy number'))
    op.add_column('loss_run_claims', sa.Column('report_date', sa.Date(), nullable=True, comment='Date claim was reported'))
    op.add_column('loss_run_claims', sa.Column('description', sa.Text(), nullable=True, comment='Claim description'))
    
    # Create policy_items table
    op.create_table('policy_items',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('document_id', sa.UUID(), nullable=True),
        sa.Column('chunk_id', sa.UUID(), nullable=True),
        sa.Column('policy_number', sa.String(), nullable=True, comment='Policy identification number'),
        sa.Column('policy_type', sa.String(), nullable=True, comment='Type of policy (Property, Auto, GL, etc.)'),
        sa.Column('insured_name', sa.String(), nullable=True, comment='Name of insured party'),
        sa.Column('effective_date', sa.Date(), nullable=True, comment='Policy effective date'),
        sa.Column('expiration_date', sa.Date(), nullable=True, comment='Policy expiration date'),
        sa.Column('premium_amount', sa.Numeric(), nullable=True, comment='Total premium'),
        sa.Column('coverage_limits', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Coverage limits by type'),
        sa.Column('deductibles', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Deductibles by coverage type'),
        sa.Column('carrier_name', sa.String(), nullable=True, comment='Insurance carrier'),
        sa.Column('agent_name', sa.String(), nullable=True, comment='Agent/broker name'),
        sa.Column('additional_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Additional fields'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default='NOW()', nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ),
        sa.ForeignKeyConstraint(['chunk_id'], ['document_chunks.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create endorsement_items table
    op.create_table('endorsement_items',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('document_id', sa.UUID(), nullable=True),
        sa.Column('chunk_id', sa.UUID(), nullable=True),
        sa.Column('endorsement_number', sa.String(), nullable=True, comment='Endorsement identifier'),
        sa.Column('policy_number', sa.String(), nullable=True, comment='Associated policy number'),
        sa.Column('effective_date', sa.Date(), nullable=True, comment='Endorsement effective date'),
        sa.Column('change_type', sa.String(), nullable=True, comment='Type of change (Addition, Deletion, Modification)'),
        sa.Column('description', sa.Text(), nullable=True, comment='Description of change'),
        sa.Column('premium_change', sa.Numeric(), nullable=True, comment='Premium impact (positive or negative)'),
        sa.Column('coverage_changes', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Coverage modifications'),
        sa.Column('additional_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Additional fields'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default='NOW()', nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ),
        sa.ForeignKeyConstraint(['chunk_id'], ['document_chunks.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create invoice_items table
    op.create_table('invoice_items',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('document_id', sa.UUID(), nullable=True),
        sa.Column('chunk_id', sa.UUID(), nullable=True),
        sa.Column('invoice_number', sa.String(), nullable=True, comment='Invoice identifier'),
        sa.Column('policy_number', sa.String(), nullable=True, comment='Associated policy number'),
        sa.Column('invoice_date', sa.Date(), nullable=True, comment='Invoice date'),
        sa.Column('due_date', sa.Date(), nullable=True, comment='Payment due date'),
        sa.Column('total_amount', sa.Numeric(), nullable=True, comment='Total invoice amount'),
        sa.Column('amount_paid', sa.Numeric(), nullable=True, comment='Amount paid to date'),
        sa.Column('balance_due', sa.Numeric(), nullable=True, comment='Remaining balance'),
        sa.Column('payment_status', sa.String(), nullable=True, comment='Status (Paid, Pending, Overdue)'),
        sa.Column('payment_method', sa.String(), nullable=True, comment='Payment method if paid'),
        sa.Column('additional_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Additional fields'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default='NOW()', nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ),
        sa.ForeignKeyConstraint(['chunk_id'], ['document_chunks.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for better query performance
    op.create_index('idx_policy_items_document_id', 'policy_items', ['document_id'])
    op.create_index('idx_policy_items_policy_number', 'policy_items', ['policy_number'])
    op.create_index('idx_endorsement_items_document_id', 'endorsement_items', ['document_id'])
    op.create_index('idx_endorsement_items_policy_number', 'endorsement_items', ['policy_number'])
    op.create_index('idx_invoice_items_document_id', 'invoice_items', ['document_id'])
    op.create_index('idx_invoice_items_policy_number', 'invoice_items', ['policy_number'])
    op.create_index('idx_invoice_items_invoice_number', 'invoice_items', ['invoice_number'])


def downgrade() -> None:
    """Downgrade schema."""
    
    # Drop indexes
    op.drop_index('idx_invoice_items_invoice_number', 'invoice_items')
    op.drop_index('idx_invoice_items_policy_number', 'invoice_items')
    op.drop_index('idx_invoice_items_document_id', 'invoice_items')
    op.drop_index('idx_endorsement_items_policy_number', 'endorsement_items')
    op.drop_index('idx_endorsement_items_document_id', 'endorsement_items')
    op.drop_index('idx_policy_items_policy_number', 'policy_items')
    op.drop_index('idx_policy_items_document_id', 'policy_items')
    
    # Drop new tables
    op.drop_table('invoice_items')
    op.drop_table('endorsement_items')
    op.drop_table('policy_items')
    
    # Remove added columns from loss_run_claims
    op.drop_column('loss_run_claims', 'description')
    op.drop_column('loss_run_claims', 'report_date')
    op.drop_column('loss_run_claims', 'policy_number')
    op.drop_constraint('fk_loss_run_claims_chunk_id', 'loss_run_claims', type_='foreignkey')
    op.drop_column('loss_run_claims', 'chunk_id')
    
    # Remove added columns from sov_items
    op.drop_column('sov_items', 'total_insured_value')
    op.drop_column('sov_items', 'bi_limit')
    op.drop_column('sov_items', 'contents_limit')
    op.drop_column('sov_items', 'building_limit')
    op.drop_column('sov_items', 'address')
    op.drop_constraint('fk_sov_items_chunk_id', 'sov_items', type_='foreignkey')
    op.drop_column('sov_items', 'chunk_id')
    
    # Restore old columns to sov_items
    op.add_column('sov_items', sa.Column('limit', sa.Numeric(), nullable=True, comment='Coverage limit'))
    op.add_column('sov_items', sa.Column('deductible', sa.Numeric(), nullable=True, comment='Deductible amount'))
