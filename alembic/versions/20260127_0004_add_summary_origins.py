"""add summary origin fields

Revision ID: 20260127_0004
Revises: 20260127_0003
Create Date: 2026-01-27 20:15:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260127_0004"
down_revision = "20260127_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "summaries",
        sa.Column(
            "summary_origin",
            sa.Text(),
            nullable=False,
            server_default="unknown",
        ),
    )
    op.add_column(
        "summaries",
        sa.Column(
            "summary_pt_origin",
            sa.Text(),
            nullable=False,
            server_default="unknown",
        ),
    )

    op.alter_column("summaries", "summary_origin", server_default=None)
    op.alter_column("summaries", "summary_pt_origin", server_default=None)


def downgrade() -> None:
    op.drop_column("summaries", "summary_pt_origin")
    op.drop_column("summaries", "summary_origin")
