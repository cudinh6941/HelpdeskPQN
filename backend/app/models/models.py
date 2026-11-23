from datetime import datetime, timezone
import enum
from typing import Optional
import uuid

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, GUID, JSONType
from app.core.uuid_utils import uuid7


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserRole(str, enum.Enum):
    END_USER = "END_USER"
    IT_AGENT = "IT_AGENT"
    IT_LEAD = "IT_LEAD"
    SYS_ADMIN = "SYS_ADMIN"


class TicketStatus(str, enum.Enum):
    NEW = "NEW"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING_FOR_USER = "WAITING_FOR_USER"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    REOPENED = "REOPENED"
    CANCELLED = "CANCELLED"


class TicketPriority(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class KbVisibility(str, enum.Enum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"


class OutboxStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SENT = "SENT"
    FAILED = "FAILED"


# 1. departments
class Department(Base):
    __tablename__ = "departments"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    users: Mapped[list["User"]] = relationship("User", back_populates="department")


# 2. users
class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    ldap_dn: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    email: Mapped[str] = mapped_column(String(180), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role", native_enum=False),
        default=UserRole.END_USER,
        nullable=False,
    )
    department_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )
    telegram_chat_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    zalo_user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    department: Mapped[Optional["Department"]] = relationship("Department", back_populates="users")
    group_memberships: Mapped[list["SupportGroupMember"]] = relationship(
        "SupportGroupMember", back_populates="user", cascade="all, delete-orphan"
    )


# 3. support_groups
class SupportGroup(Base):
    __tablename__ = "support_groups"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    members: Mapped[list["SupportGroupMember"]] = relationship(
        "SupportGroupMember", back_populates="group", cascade="all, delete-orphan"
    )


# 4. support_group_members
class SupportGroupMember(Base):
    __tablename__ = "support_group_members"
    __table_args__ = (UniqueConstraint("group_id", "user_id", name="uq_group_user"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    group_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("support_groups.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    is_lead: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    group: Mapped["SupportGroup"] = relationship("SupportGroup", back_populates="members")
    user: Mapped["User"] = relationship("User", back_populates="group_memberships")


# 5. sla_policies
class SlaPolicy(Base):
    __tablename__ = "sla_policies"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    priority: Mapped[TicketPriority] = mapped_column(
        SAEnum(TicketPriority, name="ticket_priority", native_enum=False),
        unique=True,
        nullable=False,
    )
    first_response_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    resolution_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    warning_threshold_pct: Mapped[int] = mapped_column(Integer, default=80, nullable=False)
    business_hours_only: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


# 6. business_calendars
class BusinessCalendar(Base):
    __tablename__ = "business_calendars"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Ho_Chi_Minh", nullable=False)
    work_days: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    holidays: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


# 7. categories
class Category(Base):
    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    default_group_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("support_groups.id", ondelete="SET NULL"), nullable=True
    )
    default_priority: Mapped[TicketPriority] = mapped_column(
        SAEnum(TicketPriority, name="ticket_priority", native_enum=False),
        default=TicketPriority.MEDIUM,
        nullable=False,
    )
    form_schema: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    default_group: Mapped[Optional["SupportGroup"]] = relationship("SupportGroup")


# 8. tickets
class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        Index("ix_tickets_status_priority", "status", "priority"),
        Index("ix_tickets_sla_scan", "status", "is_resolution_breached", "resolution_due_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    ticket_code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[TicketStatus] = mapped_column(
        SAEnum(TicketStatus, name="ticket_status", native_enum=False),
        default=TicketStatus.NEW,
        index=True,
        nullable=False,
    )
    priority: Mapped[TicketPriority] = mapped_column(
        SAEnum(TicketPriority, name="ticket_priority", native_enum=False),
        default=TicketPriority.MEDIUM,
        index=True,
        nullable=False,
    )

    requester_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    assignee_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    support_group_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("support_groups.id", ondelete="SET NULL"), index=True, nullable=True
    )
    category_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("categories.id", ondelete="SET NULL"), index=True, nullable=True
    )
    sla_policy_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("sla_policies.id", ondelete="SET NULL"), nullable=True
    )
    parent_ticket_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("tickets.id", ondelete="SET NULL"), index=True, nullable=True
    )

    asset_code: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    custom_data: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    first_response_due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    first_responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    sla_paused_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    total_paused_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_response_breached: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_resolution_breached: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sla_warning_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    requester: Mapped["User"] = relationship("User", foreign_keys=[requester_id])
    assignee: Mapped[Optional["User"]] = relationship("User", foreign_keys=[assignee_id])
    support_group: Mapped[Optional["SupportGroup"]] = relationship("SupportGroup")
    category: Mapped[Optional["Category"]] = relationship("Category")
    sla_policy: Mapped[Optional["SlaPolicy"]] = relationship("SlaPolicy")
    parent_ticket: Mapped[Optional["Ticket"]] = relationship(
        "Ticket", remote_side=[id], foreign_keys=[parent_ticket_id]
    )
    comments: Mapped[list["TicketComment"]] = relationship(
        "TicketComment", back_populates="ticket", cascade="all, delete-orphan", order_by="TicketComment.created_at"
    )
    attachments: Mapped[list["TicketAttachment"]] = relationship(
        "TicketAttachment", back_populates="ticket", cascade="all, delete-orphan"
    )


# 9. ticket_comments
class TicketComment(Base):
    __tablename__ = "ticket_comments"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tickets.id", ondelete="CASCADE"), index=True, nullable=False
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    kb_article_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("kb_articles.id", ondelete="SET NULL"), index=True, nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="comments")
    author: Mapped["User"] = relationship("User")
    kb_article: Mapped[Optional["KbArticle"]] = relationship("KbArticle")
    attachments: Mapped[list["TicketAttachment"]] = relationship(
        "TicketAttachment", back_populates="comment"
    )


# 10. ticket_attachments
class TicketAttachment(Base):
    __tablename__ = "ticket_attachments"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    ticket_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("tickets.id", ondelete="CASCADE"), index=True, nullable=True
    )
    comment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("ticket_comments.id", ondelete="SET NULL"), index=True, nullable=True
    )
    kb_article_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("kb_articles.id", ondelete="CASCADE"), index=True, nullable=True
    )
    uploader_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    bucket_name: Mapped[str] = mapped_column(String(120), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_uploaded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    ticket: Mapped[Optional["Ticket"]] = relationship("Ticket", back_populates="attachments")
    comment: Mapped[Optional["TicketComment"]] = relationship("TicketComment", back_populates="attachments")
    kb_article: Mapped[Optional["KbArticle"]] = relationship("KbArticle", back_populates="attachments")
    uploader: Mapped["User"] = relationship("User")


# 12. kb_articles (Dedicated Knowledge Base & IT Runbook Table)
class KbArticle(Base):
    __tablename__ = "kb_articles"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    category_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("categories.id", ondelete="SET NULL"), index=True, nullable=True
    )
    visibility: Mapped[KbVisibility] = mapped_column(
        SAEnum(KbVisibility, name="kb_visibility", native_enum=False),
        default=KbVisibility.INTERNAL,
        index=True,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    symptoms: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    root_cause: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    steps: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    keywords: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    source_ticket_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("tickets.id", ondelete="SET NULL"), index=True, nullable=True
    )
    author_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    category: Mapped[Optional["Category"]] = relationship("Category")
    source_ticket: Mapped[Optional["Ticket"]] = relationship("Ticket")
    author: Mapped[Optional["User"]] = relationship("User", foreign_keys=[author_id])
    updated_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[updated_by_id])
    attachments: Mapped[list["TicketAttachment"]] = relationship(
        "TicketAttachment", back_populates="kb_article", cascade="all, delete-orphan"
    )


# 11. outbox_events (Transactional Outbox + Audit Trail)
class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        Index("ix_outbox_pending", "status", "next_retry_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    aggregate_type: Mapped[str] = mapped_column(String(50), default="TICKET", nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(GUID(), index=True, nullable=False)
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    status: Mapped[OutboxStatus] = mapped_column(
        SAEnum(OutboxStatus, name="outbox_status", native_enum=False),
        default=OutboxStatus.PENDING,
        nullable=False,
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    actor: Mapped[Optional["User"]] = relationship("User")


# 13. system_settings (Persistent key-value configuration)
class SystemSetting(Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    updated_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


# 14. notifications (In-app notification inbox)
class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_user_read_created", "user_id", "is_read", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    ticket_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("tickets.id", ondelete="CASCADE"), index=True, nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    link_url: Mapped[str] = mapped_column(String(255), nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


# 15. canned_responses (IT Macros & Quick Replies)
class CannedResponse(Base):
    __tablename__ = "canned_responses"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    shortcut: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    category_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("categories.id", ondelete="SET NULL"), index=True, nullable=True
    )
    target_status: Mapped[Optional[TicketStatus]] = mapped_column(
        SAEnum(TicketStatus, name="ticket_status", native_enum=False), nullable=True
    )
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    category: Mapped[Optional["Category"]] = relationship("Category")
