from datetime import datetime
from typing import Any, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.models import OutboxStatus, TicketPriority, TicketStatus, UserRole


class DepartmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    code: str
    name: str
    description: Optional[str] = None
    is_active: bool


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    username: str
    email: str
    full_name: str
    role: UserRole
    department_id: Optional[uuid.UUID] = None
    department: Optional[DepartmentOut] = None
    telegram_chat_id: Optional[str] = None
    zalo_user_id: Optional[str] = None
    is_active: bool
    last_login_at: Optional[datetime] = None


class UserBriefOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    username: str
    full_name: str
    email: str
    role: UserRole


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=150)
    password: str = Field(..., min_length=1, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    auth_provider: str
    user: UserOut


class DemoAccountOut(BaseModel):
    username: str
    full_name: str
    role: UserRole
    department_name: Optional[str] = None
    default_password: str


class SupportGroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    code: str
    name: str
    description: Optional[str] = None
    is_active: bool


class SupportGroupCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=50)
    name: str = Field(..., min_length=2, max_length=120)
    description: Optional[str] = None


class SupportGroupUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=120)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class SlaPolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    priority: TicketPriority
    first_response_minutes: int
    resolution_minutes: int
    warning_threshold_pct: int
    business_hours_only: bool
    is_active: bool


class SlaPolicyUpdate(BaseModel):
    name: Optional[str] = None
    first_response_minutes: Optional[int] = Field(None, ge=1)
    resolution_minutes: Optional[int] = Field(None, ge=1)
    warning_threshold_pct: Optional[int] = Field(None, ge=10, le=99)
    business_hours_only: Optional[bool] = None
    is_active: Optional[bool] = None


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    parent_id: Optional[uuid.UUID] = None
    name: str
    slug: str
    description: Optional[str] = None
    default_group_id: Optional[uuid.UUID] = None
    default_priority: TicketPriority
    form_schema: dict[str, Any] = Field(default_factory=dict)
    is_active: bool
    sort_order: int


class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    slug: str = Field(..., min_length=2, max_length=120)
    description: Optional[str] = None
    default_group_id: Optional[uuid.UUID] = None
    default_priority: TicketPriority = TicketPriority.MEDIUM
    form_schema: dict[str, Any] = Field(default_factory=dict)
    sort_order: int = 0


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    default_group_id: Optional[uuid.UUID] = None
    default_priority: Optional[TicketPriority] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    ticket_id: Optional[uuid.UUID] = None
    comment_id: Optional[uuid.UUID] = None
    file_name: str
    content_type: str
    size_bytes: int
    is_uploaded: bool
    created_at: datetime
    download_url: str = ""


class PresignedUploadRequest(BaseModel):
    file_name: str = Field(..., min_length=1, max_length=255)
    content_type: str = Field(default="image/png", max_length=120)
    size_bytes: int = Field(default=0, ge=0, le=25 * 1024 * 1024)
    ticket_id: Optional[uuid.UUID] = None


class PresignedUploadResponse(BaseModel):
    attachment_id: uuid.UUID
    object_key: str
    upload_url: str
    direct_upload_url: str
    use_presigned: bool


class CommentCreate(BaseModel):
    body: str = Field(..., min_length=1, max_length=10000)
    is_internal: bool = False
    attachment_ids: list[uuid.UUID] = Field(default_factory=list)


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    ticket_id: uuid.UUID
    author_id: uuid.UUID
    author: UserBriefOut
    body: str
    is_internal: bool
    created_at: datetime
    attachments: list[AttachmentOut] = Field(default_factory=list)


class TimelineEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    event_type: str
    actor_id: Optional[uuid.UUID] = None
    payload: dict[str, Any]
    status: OutboxStatus
    created_at: datetime


class SlaStatusOut(BaseModel):
    state: str
    remaining_seconds: Optional[int] = None
    elapsed_pct: Optional[int] = None
    is_paused: bool = False


class TicketCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=255)
    description: str = Field(..., min_length=3, max_length=20000)
    category_id: Optional[uuid.UUID] = None
    priority: Optional[TicketPriority] = None
    asset_code: Optional[str] = Field(None, max_length=64)
    ultraview_id: Optional[str] = Field(None, max_length=32)
    ultraview_pass: Optional[str] = Field(None, max_length=32)
    custom_data: dict[str, Any] = Field(default_factory=dict)
    attachment_ids: list[uuid.UUID] = Field(default_factory=list)


class UltraViewProvideRequest(BaseModel):
    ultraview_id: str = Field(..., min_length=6, max_length=32)
    ultraview_pass: str = Field(..., min_length=3, max_length=32)


class TicketStatusUpdate(BaseModel):
    status: TicketStatus
    note: Optional[str] = Field(None, max_length=2000)


class TicketAssignRequest(BaseModel):
    assignee_id: Optional[uuid.UUID] = None
    support_group_id: Optional[uuid.UUID] = None


class TicketRateRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    feedback: Optional[str] = Field(None, max_length=2000)
    close_ticket: bool = True


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    ticket_code: str
    title: str
    description: str
    status: TicketStatus
    priority: TicketPriority
    requester_id: uuid.UUID
    requester: UserBriefOut
    assignee_id: Optional[uuid.UUID] = None
    assignee: Optional[UserBriefOut] = None
    support_group_id: Optional[uuid.UUID] = None
    support_group: Optional[SupportGroupOut] = None
    category_id: Optional[uuid.UUID] = None
    category: Optional[CategoryOut] = None
    asset_code: Optional[str] = None
    custom_data: dict[str, Any] = Field(default_factory=dict)
    first_response_due_at: Optional[datetime] = None
    first_responded_at: Optional[datetime] = None
    resolution_due_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    sla_paused_at: Optional[datetime] = None
    total_paused_seconds: int
    is_response_breached: bool
    is_resolution_breached: bool
    sla_warning_sent: bool
    rating: Optional[int] = None
    feedback: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    sla_status: Optional[SlaStatusOut] = None


class TicketDetailOut(TicketOut):
    comments: list[CommentOut] = Field(default_factory=list)
    attachments: list[AttachmentOut] = Field(default_factory=list)
    timeline: list[TimelineEventOut] = Field(default_factory=list)


class TicketListResponse(BaseModel):
    items: list[TicketOut]
    total: int


class TicketMetadataResponse(BaseModel):
    categories: list[CategoryOut]
    support_groups: list[SupportGroupOut]
    sla_policies: list[SlaPolicyOut]
    it_agents: list[UserBriefOut]


class OutboxEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    aggregate_type: str
    aggregate_id: uuid.UUID
    event_type: str
    payload: dict[str, Any]
    status: OutboxStatus
    retry_count: int
    next_retry_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    last_error: Optional[str] = None
    created_at: datetime


class UserRoleUpdate(BaseModel):
    role: UserRole
    is_active: Optional[bool] = None
    telegram_chat_id: Optional[str] = None
    zalo_user_id: Optional[str] = None


class AnalyticsSummaryOut(BaseModel):
    total_tickets: int
    open_tickets: int
    resolved_tickets: int
    breached_tickets: int
    sla_compliance_pct: float
    avg_resolution_minutes: float
    avg_first_response_minutes: float
    avg_rating: float = 0.0
    rated_count: int = 0
    by_status: dict[str, int]
    by_priority: dict[str, int]
    by_category: list[dict[str, Any]]
    by_group: list[dict[str, Any]]
    by_agent: list[dict[str, Any]] = Field(default_factory=list)
    daily_trend: list[dict[str, Any]] = Field(default_factory=list)
    top_assets: list[dict[str, Any]]


class KbArticleCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    keywords: list[str] = Field(default_factory=list)
    steps: list[str] = Field(..., min_length=1)


class AutomationSettingsOut(BaseModel):
    auto_assign_enabled: bool
    auto_close_resolved_hours: int


class AutomationSettingsUpdate(BaseModel):
    auto_assign_enabled: Optional[bool] = None
    auto_close_resolved_hours: Optional[int] = Field(None, ge=1, le=720)
