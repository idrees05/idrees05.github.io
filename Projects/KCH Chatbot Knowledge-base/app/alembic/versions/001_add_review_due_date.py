"""Add review_due_date to knowledge_items

Revision ID: 001
Revises:
Create Date: 2026-03-03
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "knowledge_items",
        sa.Column("review_due_date", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("knowledge_items", "review_due_date")
