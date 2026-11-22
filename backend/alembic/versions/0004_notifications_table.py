"""Add notifications table for persistent in-app notification inbox

Revision ID: 0004_notifications_table
Revises: 0003_system_settings_table
Create Date: 2026-11-22 14:56:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.core.database import GUID

revision: str = "0004_notifications_table"
down_revision: Union[str, None] = "0003_system_settings_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("user_id", GUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ticket_id", GUID(), sa.ForeignKey("tickets.id", ondelete="CASCADE"), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("link_url", sa.String(255), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_ticket_id", "notifications", ["ticket_id"])
    op.create_index(
        "ix_notifications_user_read_created",
        "notifications",
        ["user_id", "is_read", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_user_read_created", table_name="notifications")
    op.drop_index("ix_notifications_ticket_id", table_name="notifications")
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_table("notifications")

