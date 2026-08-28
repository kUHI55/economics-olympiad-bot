"""add stable identifiers for GitHub theory synchronization

Revision ID: 20260828_02
Revises: 20260828_01
Create Date: 2026-08-28
"""

import sqlalchemy as sa
from alembic import op

revision = "20260828_02"
down_revision = "20260828_01"
branch_labels = None
depends_on = None

EXTERNAL_ID_TABLES = (
    "sections",
    "topics",
    "subtopics",
    "sources",
    "knowledge_elements",
    "questions",
    "question_options",
)


def _column_names(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def upgrade() -> None:
    # The first migration creates metadata dynamically for fresh installations. These guards keep
    # this revision safe both for those databases and for databases created before this sync layer.
    for table_name in EXTERNAL_ID_TABLES:
        if "external_id" not in _column_names(table_name):
            op.add_column(table_name, sa.Column("external_id", sa.String(length=255), nullable=True))
        index_name = f"ix_{table_name}_external_id"
        if index_name not in _index_names(table_name):
            op.create_index(index_name, table_name, ["external_id"], unique=True)

    if "is_active" not in _column_names("knowledge_elements"):
        op.add_column(
            "knowledge_elements",
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
        )


def downgrade() -> None:
    if "is_active" in _column_names("knowledge_elements"):
        op.drop_column("knowledge_elements", "is_active")
    for table_name in reversed(EXTERNAL_ID_TABLES):
        index_name = f"ix_{table_name}_external_id"
        if index_name in _index_names(table_name):
            op.drop_index(index_name, table_name=table_name)
        if "external_id" in _column_names(table_name):
            op.drop_column(table_name, "external_id")
