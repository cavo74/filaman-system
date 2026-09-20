"""merge source_event_key backport with upstream tag-reader migrations

Revision ID: 0f8644d53c84
Revises: add_spool_event_source_key, f3c7a1e9d204
Create Date: 2026-09-20 20:34:46.752737

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0f8644d53c84'
down_revision: Union[str, Sequence[str], None] = ('add_spool_event_source_key', 'f3c7a1e9d204')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
