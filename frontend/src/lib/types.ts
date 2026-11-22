export type UserRole = "END_USER" | "IT_AGENT" | "IT_LEAD" | "SYS_ADMIN";

export type TicketStatus =
  | "NEW"
  | "ASSIGNED"
  | "IN_PROGRESS"
  | "WAITING_FOR_USER"
  | "RESOLVED"
  | "CLOSED"
  | "REOPENED"
  | "CANCELLED";

export type TicketPriority = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export interface Department {
  id: string;
  code: string;
  name: string;
  description?: string | null;
  is_active: boolean;
}

export interface User {
  id: string;
  username: string;
  email: string;
  full_name: string;
  role: UserRole;
  department_id?: string | null;
  department?: Department | null;
  telegram_chat_id?: string | null;
  zalo_user_id?: string | null;
  is_active: boolean;
  last_login_at?: string | null;
}

export interface UserBrief {
  id: string;
  username: string;
  full_name: string;
  email: string;
  role: UserRole;
}

export interface DemoAccount {
  username: string;
  full_name: string;
  role: UserRole;
  department_name?: string | null;
  default_password: string;
}

export interface SupportGroup {
  id: string;
  code: string;
  name: string;
  description?: string | null;
  is_active: boolean;
}

export interface SupportGroupMember {
  id: string;
  user_id: string;
  is_lead: boolean;
  user: UserBrief;
}

export interface SupportGroupDetail extends SupportGroup {
  members: SupportGroupMember[];
}

export interface BusinessCalendar {
  id: string;
  name: string;
  timezone: string;
  work_days: Record<string, [string, string]>;
  holidays: string[];
  is_default: boolean;
}

export interface NotificationItem {
  id: string;
  user_id: string;
  ticket_id?: string | null;
  event_type: string;
  title: string;
  body: string;
  link_url: string;
  is_read: boolean;
  created_at: string;
}

export interface NotificationListResponse {
  items: NotificationItem[];
  unread_count: number;
}

export interface TicketBulkActionResponse {
  updated: number;
  skipped: number;
  errors: string[];
}

export interface SlaPolicy {
  id: string;
  name: string;
  priority: TicketPriority;
  first_response_minutes: number;
  resolution_minutes: number;
  warning_threshold_pct: number;
  business_hours_only: boolean;
  is_active: boolean;
}

export type KbVisibility = "PUBLIC" | "INTERNAL";

export interface KbArticle {
  id: string;
  title: string;
  keywords: string[];
  steps: string[];
}

export interface KbSourceTicketBrief {
  id: string;
  ticket_code: string;
  title: string;
}

export interface KbArticleDetail {
  id: string;
  category_id?: string | null;
  category?: Category | null;
  visibility: KbVisibility;
  title: string;
  symptoms?: string | null;
  root_cause?: string | null;
  steps: string[];
  notes?: string | null;
  keywords: string[];
  source_ticket_id?: string | null;
  source_ticket?: KbSourceTicketBrief | null;
  author_id?: string | null;
  author?: UserBrief | null;
  updated_by_id?: string | null;
  updated_by?: UserBrief | null;
  is_active: boolean;
  attachments: Attachment[];
  created_at: string;
  updated_at: string;
}

export interface AutomationSettings {
  auto_assign_enabled: boolean;
  auto_close_resolved_hours: number;
}

export interface Category {
  id: string;
  parent_id?: string | null;
  name: string;
  slug: string;
  description?: string | null;
  default_group_id?: string | null;
  default_priority: TicketPriority;
  form_schema?: {
    kb_articles?: KbArticle[];
    [key: string]: unknown;
  };
  is_active: boolean;
  sort_order: number;
}

export interface Attachment {
  id: string;
  ticket_id?: string | null;
  comment_id?: string | null;
  kb_article_id?: string | null;
  file_name: string;
  content_type: string;
  size_bytes: number;
  is_uploaded: boolean;
  created_at: string;
  download_url: string;
}

export interface TicketComment {
  id: string;
  ticket_id: string;
  author_id: string;
  author: UserBrief;
  body: string;
  is_internal: boolean;
  created_at: string;
  attachments: Attachment[];
}

export interface TimelineEvent {
  id: string;
  event_type: string;
  actor_id?: string | null;
  payload: Record<string, any>;
  status: string;
  created_at: string;
}

export interface SlaStatus {
  state: "ON_TRACK" | "WARNING" | "BREACHED" | "PAUSED" | "MET";
  remaining_seconds?: number | null;
  elapsed_pct?: number | null;
  is_paused: boolean;
}

export interface Ticket {
  id: string;
  ticket_code: string;
  title: string;
  description: string;
  status: TicketStatus;
  priority: TicketPriority;
  requester_id: string;
  requester: UserBrief;
  assignee_id?: string | null;
  assignee?: UserBrief | null;
  support_group_id?: string | null;
  support_group?: SupportGroup | null;
  category_id?: string | null;
  category?: Category | null;
  parent_ticket_id?: string | null;
  asset_code?: string | null;
  custom_data: Record<string, any>;
  first_response_due_at?: string | null;
  first_responded_at?: string | null;
  resolution_due_at?: string | null;
  resolved_at?: string | null;
  closed_at?: string | null;
  sla_paused_at?: string | null;
  total_paused_seconds: number;
  is_response_breached: boolean;
  is_resolution_breached: boolean;
  sla_warning_sent: boolean;
  rating?: number | null;
  feedback?: string | null;
  created_at: string;
  updated_at: string;
  sla_status?: SlaStatus | null;
}

export interface TicketDetail extends Ticket {
  comments: TicketComment[];
  attachments: Attachment[];
  timeline: TimelineEvent[];
}

export interface TicketMetadata {
  categories: Category[];
  support_groups: SupportGroup[];
  sla_policies: SlaPolicy[];
  it_agents: UserBrief[];
  requesters?: UserBrief[];
}

export interface TicketBrief {
  id: string;
  ticket_code: string;
  title: string;
  status: TicketStatus;
  priority: TicketPriority;
  asset_code?: string | null;
  created_at: string;
}

export interface TicketRelated {
  by_asset: TicketBrief[];
  by_requester: TicketBrief[];
  parent?: TicketBrief | null;
  children: TicketBrief[];
}

export interface CannedResponse {
  id: string;
  shortcut: string;
  title: string;
  body: string;
  category_id?: string | null;
  target_status?: TicketStatus | null;
  is_internal: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface OutboxEvent {
  id: string;
  aggregate_type: string;
  aggregate_id: string;
  event_type: string;
  payload: Record<string, any>;
  status: "PENDING" | "PROCESSING" | "SENT" | "FAILED";
  retry_count: number;
  next_retry_at?: string | null;
  processed_at?: string | null;
  last_error?: string | null;
  created_at: string;
}

export interface AnalyticsSummary {
  total_tickets: number;
  open_tickets: number;
  resolved_tickets: number;
  breached_tickets: number;
  sla_compliance_pct: number;
  avg_resolution_minutes: number;
  avg_first_response_minutes: number;
  avg_rating: number;
  rated_count: number;
  by_status: Record<string, number>;
  by_priority: Record<string, number>;
  by_category: Array<{ name: string; count: number }>;
  by_group: Array<{ name: string; count: number }>;
  by_agent: Array<{
    agent_name: string;
    assigned_count: number;
    resolved_count: number;
    breached_count: number;
    avg_resolution_minutes: number;
  }>;
  daily_trend: Array<{
    date: string;
    created_count: number;
    resolved_count: number;
    breached_count: number;
  }>;
  top_assets: Array<{ asset_code: string; count: number }>;
}
