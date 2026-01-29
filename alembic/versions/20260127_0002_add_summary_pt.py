"""add summary_pt column

Revision ID: 20260127_0002
Revises: 20260127_0001
Create Date: 2026-01-27 13:40:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260127_0002"
down_revision = "20260127_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("summaries", sa.Column("summary_pt", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("summaries", "summary_pt")
