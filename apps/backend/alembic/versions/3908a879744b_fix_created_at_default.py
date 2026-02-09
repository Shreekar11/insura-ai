"""fix_created_at_default

Revision ID: 3908a879744b
Revises: 7fac5ae0e6ed
Create Date: 2026-01-29 12:38:24.680815

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3908a879744b'
down_revision: Union[str, Sequence[str], None] = '7fac5ae0e6ed'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TABLE workflows ALTER COLUMN created_at SET DEFAULT now()")
    op.execute("ALTER TABLE workflow_documents ALTER COLUMN created_at SET DEFAULT now()")


def downgrade() -> None:
    """Downgrade schema."""
    pass
