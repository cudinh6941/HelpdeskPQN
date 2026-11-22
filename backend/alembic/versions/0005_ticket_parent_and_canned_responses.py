"""Add parent_ticket_id on tickets and canned_responses table for IT macros

Revision ID: 0005_ticket_parent_and_canned_responses
Revises: 0004_notifications_table
Create Date: 2026-11-22 15:07:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.core.database import GUID

revision: str = "0005_parent_and_macros"
down_revision: Union[str, None] = "0004_notifications_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("parent_ticket_id", GUID(), nullable=True))
    op.create_foreign_key(
        "fk_tickets_parent_ticket_id",
        "tickets",
        "tickets",
        ["parent_ticket_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_tickets_parent_ticket_id", "tickets", ["parent_ticket_id"])

    op.create_table(
        "canned_responses",
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("shortcut", sa.String(50), nullable=False),
        sa.Column("title", sa.String(150), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "category_id",
            GUID(),
            sa.ForeignKey("categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("target_status", sa.String(32), nullable=True),
        sa.Column("is_internal", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_by_id",
            GUID(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_canned_responses_shortcut", "canned_responses", ["shortcut"], unique=True)
    op.create_index("ix_canned_responses_category_id", "canned_responses", ["category_id"])


def downgrade() -> None:
    op.drop_index("ix_canned_responses_category_id", table_name="canned_responses")
    op.drop_index("ix_canned_responses_shortcut", table_name="canned_responses")
    op.drop_table("canned_responses")

    op.drop_index("ix_tickets_parent_ticket_id", table_name="tickets")
    op.drop_constraint("fk_tickets_parent_ticket_id", "tickets", type_="foreignkey")
    op.drop_column("tickets", "parent_ticket_id")

