"""add word_count column and unique constraint

Revision ID: 20260127_0003
Revises: 20260127_0002
Create Date: 2026-01-27 15:30:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260127_0003"
down_revision = "20260127_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "summaries",
        sa.Column("word_count", sa.Integer(), nullable=False, server_default="0"),
    )

    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, summary FROM summaries")).fetchall()
    for row in rows:
        summary_text = row.summary or ""
        word_count = len(summary_text.split())
        connection.execute(
            sa.text("UPDATE summaries SET word_count = :word_count WHERE id = :id"),
            {"word_count": word_count, "id": row.id},
        )

    op.alter_column("summaries", "word_count", server_default=None)

    op.drop_index("ix_summaries_url", table_name="summaries")
    op.create_index("ix_summaries_url", "summaries", ["url"], unique=False)
    op.create_unique_constraint(
        "uq_summaries_url_word_count",
        "summaries",
        ["url", "word_count"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_summaries_url_word_count", "summaries", type_="unique")
    op.drop_index("ix_summaries_url", table_name="summaries")
    op.create_index("ix_summaries_url", "summaries", ["url"], unique=True)
    op.drop_column("summaries", "word_count")
