"""Add kb_article_id foreign key to ticket_comments

Revision ID: 0006_comment_kb_article
Revises: 0005_parent_and_macros
Create Date: 2026-11-23 16:55:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.core.database import GUID

revision: str = "0006_comment_kb_article"
down_revision: Union[str, None] = "0005_parent_and_macros"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("ticket_comments", sa.Column("kb_article_id", GUID(), nullable=True))
    op.create_foreign_key(
        "fk_ticket_comments_kb_article_id",
        "ticket_comments",
        "kb_articles",
        ["kb_article_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_ticket_comments_kb_article_id", "ticket_comments", ["kb_article_id"])


def downgrade() -> None:
    op.drop_index("ix_ticket_comments_kb_article_id", table_name="ticket_comments")
    op.drop_constraint("fk_ticket_comments_kb_article_id", "ticket_comments", type_="foreignkey")
    op.drop_column("ticket_comments", "kb_article_id")
