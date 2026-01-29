"""create summaries table

Revision ID: 20260127_0001
Revises:
Create Date: 2026-01-27 12:40:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260127_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "summaries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_summaries_url", "summaries", ["url"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_summaries_url", table_name="summaries")
    op.drop_table("summaries")
