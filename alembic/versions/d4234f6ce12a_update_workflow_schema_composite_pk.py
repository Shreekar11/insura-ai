"""update_workflow_schema_composite_pk

Revision ID: d4234f6ce12a
Revises: d4234f6ce12a
Create Date: 2026-01-04 19:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd4234f6ce12a'
down_revision: Union[str, Sequence[str], None] = '91234f6ce12a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - ensure workflow_documents uses composite PK.
    
    Changes:
    1. Ensure workflow_documents has composite primary key (document_id, workflow_id)
    2. Ensure both document_id and workflow_id are NOT NULL
    3. Add updated_at column to workflow_documents
    4. Add updated_at columns to workflow_run_events, workflow_definitions
    5. Add created_at and updated_at to workflow_entity_scope, workflow_relationship_scope
    6. Drop workflow_type column from workflows (superseded by workflow_definition)
    """
    
    # Step 1: Check current state of workflow_documents table
    connection = op.get_bind()
    
    # Check if we need to modify the primary key
    result = connection.execute(sa.text("""
        SELECT constraint_name
        FROM information_schema.table_constraints
        WHERE table_name = 'workflow_documents' 
        AND constraint_type = 'PRIMARY KEY'
    """))
    pk_constraint = result.fetchone()
    
    if pk_constraint:
        # Drop existing primary key if it exists
        op.drop_constraint(pk_constraint[0], 'workflow_documents', type_='primary')
    
    # Step 2: Ensure both columns are NOT NULL
    op.alter_column('workflow_documents', 'workflow_id',
        existing_type=sa.UUID(),
        nullable=False
    )
    
    op.alter_column('workflow_documents', 'document_id',
        existing_type=sa.UUID(),
        nullable=False
    )
    
    # Step 3: Create composite primary key on (document_id, workflow_id)
    op.create_primary_key(
        'workflow_documents_pkey', 
        'workflow_documents', 
        ['document_id', 'workflow_id']
    )
    
    # Step 4: Add updated_at column to workflow_documents if not exists
    result = connection.execute(sa.text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='workflow_documents' AND column_name='updated_at'
    """))
    if not result.fetchone():
        op.add_column('workflow_documents',
            sa.Column('updated_at', sa.TIMESTAMP(timezone=True), 
                      server_default=sa.text('NOW()'), nullable=False)
        )
    
    # Step 5: Add updated_at column to workflow_run_events if not exists
    result = connection.execute(sa.text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='workflow_run_events' AND column_name='updated_at'
    """))
    if not result.fetchone():
        op.add_column('workflow_run_events',
            sa.Column('updated_at', sa.TIMESTAMP(timezone=True), 
                      server_default=sa.text('NOW()'), nullable=False)
        )
    
    # Step 6: Add updated_at column to workflow_definitions if not exists
    result = connection.execute(sa.text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='workflow_definitions' AND column_name='updated_at'
    """))
    if not result.fetchone():
        op.add_column('workflow_definitions',
            sa.Column('updated_at', sa.TIMESTAMP(timezone=True), 
                      server_default=sa.text('NOW()'), nullable=False)
        )
    
    # Step 7: Add timestamp columns to workflow_entity_scope if not exists
    result = connection.execute(sa.text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='workflow_entity_scope' AND column_name='created_at'
    """))
    if not result.fetchone():
        op.add_column('workflow_entity_scope',
            sa.Column('created_at', sa.TIMESTAMP(timezone=True), 
                      server_default=sa.text('NOW()'), nullable=False)
        )
    
    result = connection.execute(sa.text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='workflow_entity_scope' AND column_name='updated_at'
    """))
    if not result.fetchone():
        op.add_column('workflow_entity_scope',
            sa.Column('updated_at', sa.TIMESTAMP(timezone=True), 
                      server_default=sa.text('NOW()'), nullable=False)
        )
    
    # Step 8: Add timestamp columns to workflow_relationship_scope if not exists
    result = connection.execute(sa.text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='workflow_relationship_scope' AND column_name='created_at'
    """))
    if not result.fetchone():
        op.add_column('workflow_relationship_scope',
            sa.Column('created_at', sa.TIMESTAMP(timezone=True), 
                      server_default=sa.text('NOW()'), nullable=False)
        )
    
    result = connection.execute(sa.text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='workflow_relationship_scope' AND column_name='updated_at'
    """))
    if not result.fetchone():
        op.add_column('workflow_relationship_scope',
            sa.Column('updated_at', sa.TIMESTAMP(timezone=True), 
                      server_default=sa.text('NOW()'), nullable=False)
        )
    
    # Step 9: Drop workflow_type column if it exists (replaced by workflow_definition)
    result = connection.execute(sa.text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='workflows' AND column_name='workflow_type'
    """))
    if result.fetchone():
        op.drop_column('workflows', 'workflow_type')

    # Step 10: Drop orphaned id column from workflow_documents
    result = connection.execute(sa.text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='workflow_documents' AND column_name='id'
    """))
    if result.fetchone():
        op.drop_column('workflow_documents', 'id')

    # Step 11: Drop orphaned workflow_document_id from workflows
    result = connection.execute(sa.text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='workflows' AND column_name='workflow_document_id'
    """))
    if result.fetchone():
        # First drop constraint if exists
        op.execute("ALTER TABLE workflows DROP CONSTRAINT IF EXISTS fk_workflows_workflow_document_id")
        op.drop_column('workflows', 'workflow_document_id')


def downgrade() -> None:
    """Downgrade schema back to previous state.
    
    Warning: This will lose data and may break relationships.
    """
    
    # Step 1: Add back workflow_document_id and its FK
    op.add_column('workflows',
        sa.Column('workflow_document_id', sa.UUID(), nullable=True)
    )
    op.create_foreign_key(
        'fk_workflows_workflow_document_id',
        'workflows',
        'workflow_documents',
        ['workflow_document_id'],
        ['id'],
        ondelete='CASCADE'
    )
    
    # Step 2: Add back id column to workflow_documents
    op.add_column('workflow_documents', 
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()'))
    )

    # Step 3: Add back workflow_type column
    op.add_column('workflows',
        sa.Column('workflow_type', sa.String(), nullable=True)
    )
    
    # Step 4: Populate workflow_type from workflow_definition if possible
    op.execute("""
        UPDATE workflows w
        SET workflow_type = wd.workflow_key
        FROM workflow_definitions wd
        WHERE w.workflow_definition_id = wd.id
        AND w.workflow_type IS NULL;
    """)
    
    # Step 5: Set default workflow_type for any workflows without definition
    op.execute("""
        UPDATE workflows
        SET workflow_type = 'document_extraction'
        WHERE workflow_type IS NULL;
    """)
    
    # Step 6: Make workflow_type NOT NULL
    op.alter_column('workflows', 'workflow_type',
        existing_type=sa.String(),
        nullable=False
    )
    
    # Step 7: Remove timestamp columns from workflow_relationship_scope
    connection = op.get_bind()
    result = connection.execute(sa.text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='workflow_relationship_scope' AND column_name='updated_at'
    """))
    if result.fetchone():
        op.drop_column('workflow_relationship_scope', 'updated_at')
    
    result = connection.execute(sa.text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='workflow_relationship_scope' AND column_name='created_at'
    """))
    if result.fetchone():
        op.drop_column('workflow_relationship_scope', 'created_at')
    
    # Step 8: Remove timestamp columns from workflow_entity_scope
    result = connection.execute(sa.text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='workflow_entity_scope' AND column_name='updated_at'
    """))
    if result.fetchone():
        op.drop_column('workflow_entity_scope', 'updated_at')
    
    result = connection.execute(sa.text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='workflow_entity_scope' AND column_name='created_at'
    """))
    if result.fetchone():
        op.drop_column('workflow_entity_scope', 'created_at')
    
    # Step 9: Remove updated_at from workflow_definitions
    result = connection.execute(sa.text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='workflow_definitions' AND column_name='updated_at'
    """))
    if result.fetchone():
        op.drop_column('workflow_definitions', 'updated_at')
    
    # Step 10: Remove updated_at from workflow_run_events
    result = connection.execute(sa.text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='workflow_run_events' AND column_name='updated_at'
    """))
    if result.fetchone():
        op.drop_column('workflow_run_events', 'updated_at')
    
    # Step 11: Remove updated_at from workflow_documents
    result = connection.execute(sa.text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='workflow_documents' AND column_name='updated_at'
    """))
    if result.fetchone():
        op.drop_column('workflow_documents', 'updated_at')
    
    # Note: We don't change the composite primary key structure in downgrade
    # as the original migration already had this structure