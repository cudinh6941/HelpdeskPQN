"""Initial 11-table IT Helpdesk schema with UUIDv7 and Outbox

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-11-18 13:35:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.core.database import GUID, JSONType

revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "departments",
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_departments_code", "departments", ["code"], unique=True)

    op.create_table(
        "users",
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("username", sa.String(100), nullable=False),
        sa.Column("ldap_dn", sa.String(255), nullable=True),
        sa.Column("email", sa.String(180), nullable=False),
        sa.Column("full_name", sa.String(150), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("department_id", GUID(), sa.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("telegram_chat_id", sa.String(64), nullable=True),
        sa.Column("zalo_user_id", sa.String(64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "support_groups",
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_support_groups_code", "support_groups", ["code"], unique=True)

    op.create_table(
        "support_group_members",
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("group_id", GUID(), sa.ForeignKey("support_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", GUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_lead", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("group_id", "user_id", name="uq_group_user"),
    )

    op.create_table(
        "sla_policies",
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("priority", sa.String(32), nullable=False, unique=True),
        sa.Column("first_response_minutes", sa.Integer(), nullable=False),
        sa.Column("resolution_minutes", sa.Integer(), nullable=False),
        sa.Column("warning_threshold_pct", sa.Integer(), nullable=False, server_default="80"),
        sa.Column("business_hours_only", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )

    op.create_table(
        "business_calendars",
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("work_days", JSONType, nullable=False),
        sa.Column("holidays", JSONType, nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    op.create_table(
        "categories",
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("parent_id", GUID(), sa.ForeignKey("categories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("slug", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("default_group_id", GUID(), sa.ForeignKey("support_groups.id", ondelete="SET NULL"), nullable=True),
        sa.Column("default_priority", sa.String(32), nullable=False),
        sa.Column("form_schema", JSONType, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_categories_slug", "categories", ["slug"], unique=True)

    op.create_table(
        "tickets",
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("ticket_code", sa.String(32), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("priority", sa.String(32), nullable=False),
        sa.Column("requester_id", GUID(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("assignee_id", GUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("support_group_id", GUID(), sa.ForeignKey("support_groups.id", ondelete="SET NULL"), nullable=True),
        sa.Column("category_id", GUID(), sa.ForeignKey("categories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("sla_policy_id", GUID(), sa.ForeignKey("sla_policies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("asset_code", sa.String(64), nullable=True),
        sa.Column("custom_data", JSONType, nullable=False),
        sa.Column("first_response_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sla_paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_paused_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_response_breached", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_resolution_breached", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sla_warning_sent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tickets_ticket_code", "tickets", ["ticket_code"], unique=True)
    op.create_index("ix_tickets_status", "tickets", ["status"])
    op.create_index("ix_tickets_priority", "tickets", ["priority"])
    op.create_index("ix_tickets_requester_id", "tickets", ["requester_id"])
    op.create_index("ix_tickets_assignee_id", "tickets", ["assignee_id"])
    op.create_index("ix_tickets_support_group_id", "tickets", ["support_group_id"])
    op.create_index("ix_tickets_category_id", "tickets", ["category_id"])
    op.create_index("ix_tickets_asset_code", "tickets", ["asset_code"])
    op.create_index("ix_tickets_created_at", "tickets", ["created_at"])
    op.create_index("ix_tickets_status_priority", "tickets", ["status", "priority"])
    op.create_index("ix_tickets_sla_scan", "tickets", ["status", "is_resolution_breached", "resolution_due_at"])

    op.create_table(
        "ticket_comments",
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("ticket_id", GUID(), sa.ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", GUID(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_internal", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ticket_comments_ticket_id", "ticket_comments", ["ticket_id"])

    op.create_table(
        "ticket_attachments",
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("ticket_id", GUID(), sa.ForeignKey("tickets.id", ondelete="CASCADE"), nullable=True),
        sa.Column("comment_id", GUID(), sa.ForeignKey("ticket_comments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("uploader_id", GUID(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("bucket_name", sa.String(120), nullable=False),
        sa.Column("object_key", sa.String(512), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_uploaded", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ticket_attachments_ticket_id", "ticket_attachments", ["ticket_id"])
    op.create_index("ix_ticket_attachments_comment_id", "ticket_attachments", ["comment_id"])
    op.create_index("ix_ticket_attachments_object_key", "ticket_attachments", ["object_key"], unique=True)

    op.create_table(
        "outbox_events",
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("aggregate_type", sa.String(50), nullable=False),
        sa.Column("aggregate_id", GUID(), nullable=False),
        sa.Column("actor_id", GUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("payload", JSONType, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_outbox_events_aggregate_id", "outbox_events", ["aggregate_id"])
    op.create_index("ix_outbox_events_event_type", "outbox_events", ["event_type"])
    op.create_index("ix_outbox_pending", "outbox_events", ["status", "next_retry_at", "created_at"])


def downgrade() -> None:
    op.drop_table("outbox_events")
    op.drop_table("ticket_attachments")
    op.drop_table("ticket_comments")
    op.drop_table("tickets")
    op.drop_table("categories")
    op.drop_table("business_calendars")
    op.drop_table("sla_policies")
    op.drop_table("support_group_members")
    op.drop_table("support_groups")
    op.drop_table("users")
    op.drop_table("departments")
