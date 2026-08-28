"""initial source-grounded learning schema

Revision ID: 20260828_01
Revises:
Create Date: 2026-08-28
"""

from alembic import op

import app.database.models  # noqa: F401
from app.database.base import Base

revision = "20260828_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
