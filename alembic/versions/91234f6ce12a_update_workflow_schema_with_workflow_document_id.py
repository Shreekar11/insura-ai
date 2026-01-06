"""update_workflow_schema_with_workflow_document_id

Revision ID: 91234f6ce12a
Revises: 90128e5be98e
Create Date: 2026-01-04 19:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '91234f6ce12a'
down_revision: Union[str, Sequence[str], None] = '90128e5be98e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to support workflow_document_id in workflows table.
    
    Changes:
    1. Add 'id' column to workflow_documents (making it a proper entity table)
    2. Change workflow_documents primary key to 'id'
    3. Make workflow_id nullable in workflow_documents (supports initial creation)
    4. Add unique constraint on (workflow_id, document_id) in workflow_documents
    5. Add workflow_document_id column to workflows table
    6. Add foreign key from workflows.workflow_document_id to workflow_documents.id
    7. Remove workflow_type column from workflows (superseded by workflow_definition)
    """
    
    # Step 1: Add id column to workflow_documents
    op.add_column('workflow_documents', 
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()'))
    )
    
    # Step 2: Drop existing primary key constraint (workflow_id, document_id)
    op.drop_constraint('workflow_documents_pkey', 'workflow_documents', type_='primary')
    
    # Step 3: Create new primary key on id column
    op.create_primary_key('workflow_documents_pkey', 'workflow_documents', ['id'])
    
    # Step 4: Make workflow_id nullable in workflow_documents (can be NULL initially)
    op.alter_column('workflow_documents', 'workflow_id',
        existing_type=sa.UUID(),
        nullable=True
    )
    
    # Step 5: Add unique constraint on (workflow_id, document_id) to maintain data integrity
    # Use partial unique index to allow NULL workflow_id but enforce uniqueness when set
    op.create_index(
        'idx_workflow_documents_workflow_document_unique',
        'workflow_documents',
        ['workflow_id', 'document_id'],
        unique=True,
        postgresql_where=sa.text('workflow_id IS NOT NULL')
    )
    
    # Step 6: Add workflow_document_id column to workflows table
    op.add_column('workflows',
        sa.Column('workflow_document_id', sa.UUID(), nullable=True)
    )
    
    # Step 7: Create foreign key constraint from workflows to workflow_documents
    op.create_foreign_key(
        'fk_workflows_workflow_document_id',
        'workflows',
        'workflow_documents',
        ['workflow_document_id'],
        ['id'],
        ondelete='CASCADE'
    )
    
    # Step 8: Data migration for existing workflows
    # Create workflow_documents entries for any existing workflows that don't have them
    op.execute("""
        -- First, ensure we have at least one document per workflow
        INSERT INTO workflow_documents (id, workflow_id, document_id, created_at)
        SELECT 
            gen_random_uuid() as id,
            w.id as workflow_id,
            d.id as document_id,
            w.created_at as created_at
        FROM workflows w
        CROSS JOIN LATERAL (
            SELECT id FROM documents ORDER BY created_at DESC LIMIT 1
        ) d
        WHERE NOT EXISTS (
            SELECT 1 FROM workflow_documents wd WHERE wd.workflow_id = w.id
        )
        AND w.workflow_document_id IS NULL
        ON CONFLICT DO NOTHING;
    """)
    
    # Step 9: Update workflows to reference their workflow_documents
    op.execute("""
        UPDATE workflows w
        SET workflow_document_id = wd.id
        FROM workflow_documents wd
        WHERE wd.workflow_id = w.id
        AND w.workflow_document_id IS NULL;
    """)
    
    # Step 10: Make workflow_document_id NOT NULL after data migration
    op.alter_column('workflows', 'workflow_document_id',
        existing_type=sa.UUID(),
        nullable=False
    )
    
    # Step 11: Drop workflow_type column if it exists (replaced by workflow_definition)
    connection = op.get_bind()
    result = connection.execute(sa.text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='workflows' AND column_name='workflow_type'
    """))
    if result.fetchone():
        op.drop_column('workflows', 'workflow_type')


def downgrade() -> None:
    """Downgrade schema back to previous state.
    
    Warning: This will lose data if workflow_document relationships have been created.
    """
    
    # Step 1: Add back workflow_type column
    op.add_column('workflows',
        sa.Column('workflow_type', sa.String(), nullable=True)
    )
    
    # Step 2: Populate workflow_type from workflow_definition if possible
    op.execute("""
        UPDATE workflows w
        SET workflow_type = wd.workflow_key
        FROM workflow_definitions wd
        WHERE w.workflow_definition_id = wd.id
        AND w.workflow_type IS NULL;
    """)
    
    # Step 3: Set default workflow_type for any workflows without definition
    op.execute("""
        UPDATE workflows
        SET workflow_type = 'document_extraction'
        WHERE workflow_type IS NULL;
    """)
    
    # Step 4: Make workflow_type NOT NULL
    op.alter_column('workflows', 'workflow_type',
        existing_type=sa.String(),
        nullable=False
    )
    
    # Step 5: Make workflow_document_id nullable before dropping constraint
    op.alter_column('workflows', 'workflow_document_id',
        existing_type=sa.UUID(),
        nullable=True
    )
    
    # Step 6: Drop foreign key constraint
    op.drop_constraint('fk_workflows_workflow_document_id', 'workflows', type_='foreignkey')
    
    # Step 7: Drop workflow_document_id column
    op.drop_column('workflows', 'workflow_document_id')
    
    # Step 8: Delete any workflow_documents records with NULL workflow_id
    op.execute("DELETE FROM workflow_documents WHERE workflow_id IS NULL")
    
    # Step 9: Make workflow_id NOT NULL again in workflow_documents
    op.alter_column('workflow_documents', 'workflow_id',
        existing_type=sa.UUID(),
        nullable=False
    )
    
    # Step 10: Drop unique index
    op.drop_index('idx_workflow_documents_workflow_document_unique', 'workflow_documents')
    
    # Step 11: Drop id column primary key
    op.drop_constraint('workflow_documents_pkey', 'workflow_documents', type_='primary')
    
    # Step 12: Recreate composite primary key
    op.create_primary_key('workflow_documents_pkey', 'workflow_documents', ['workflow_id', 'document_id'])
    
    # Step 13: Drop id column
    op.drop_column('workflow_documents', 'id')