"""Add system_settings table for persistent automation and runtime configuration

Revision ID: 0003_system_settings_table
Revises: 0002_kb_articles_table
Create Date: 2026-11-22 14:48:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.core.database import GUID, JSONType

revision: str = "0003_system_settings_table"
down_revision: Union[str, None] = "0002_kb_articles_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(100), primary_key=True, nullable=False),
        sa.Column("value", JSONType, nullable=False),
        sa.Column("updated_by_id", GUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("system_settings")

