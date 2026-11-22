"""Add dedicated kb_articles table and kb_article_id on ticket_attachments

Revision ID: 0002_kb_articles_table
Revises: 0001_initial_schema
Create Date: 2026-11-19 10:15:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.core.database import GUID, JSONType

revision: str = "0002_kb_articles_table"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kb_articles",
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("category_id", GUID(), sa.ForeignKey("categories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("visibility", sa.String(20), nullable=False, server_default="INTERNAL"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("symptoms", sa.Text(), nullable=True),
        sa.Column("root_cause", sa.Text(), nullable=True),
        sa.Column("steps", JSONType, nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("keywords", JSONType, nullable=False),
        sa.Column("source_ticket_id", GUID(), sa.ForeignKey("tickets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("author_id", GUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by_id", GUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_kb_articles_category_id", "kb_articles", ["category_id"])
    op.create_index("ix_kb_articles_visibility", "kb_articles", ["visibility"])
    op.create_index("ix_kb_articles_source_ticket_id", "kb_articles", ["source_ticket_id"])

    op.add_column(
        "ticket_attachments",
        sa.Column("kb_article_id", GUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_ticket_attachments_kb_article_id",
        "ticket_attachments",
        "kb_articles",
        ["kb_article_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_ticket_attachments_kb_article_id", "ticket_attachments", ["kb_article_id"])


def downgrade() -> None:
    op.drop_index("ix_ticket_attachments_kb_article_id", table_name="ticket_attachments")
    op.drop_constraint("fk_ticket_attachments_kb_article_id", "ticket_attachments", type_="foreignkey")
    op.drop_column("ticket_attachments", "kb_article_id")

    op.drop_index("ix_kb_articles_source_ticket_id", table_name="kb_articles")
    op.drop_index("ix_kb_articles_visibility", table_name="kb_articles")
    op.drop_index("ix_kb_articles_category_id", table_name="kb_articles")
    op.drop_table("kb_articles")
