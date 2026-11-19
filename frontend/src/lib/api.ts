import {
  AnalyticsSummary,
  Attachment,
  AutomationSettings,
  Category,
  DemoAccount,
  KbArticleDetail,
  KbVisibility,
  OutboxEvent,
  SlaPolicy,
  SupportGroup,
  TicketComment,
  TicketDetail,
  TicketMetadata,
  TicketPriority,
  TicketStatus,
  Ticket,
  User,
  UserRole,
} from "./types";

const ENV_API = process.env.NEXT_PUBLIC_API_URL;
export const API_BASE =
  ENV_API !== undefined ? ENV_API.replace(/\/$/, "") : "http://localhost:8000";

const TOKEN_STORAGE_KEY = "helpdesk_jwt_token";

export function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function setStoredToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token) {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
  } else {
    window.localStorage.removeItem(TOKEN_STORAGE_KEY);
  }
}

export function buildAttachmentUrl(downloadPath: string): string {
  const token = getStoredToken();
  const base = downloadPath.startsWith("http") ? downloadPath : `${API_BASE}${downloadPath}`;
  if (!token) return base;
  const sep = base.includes("?") ? "&" : "?";
  return `${base}${sep}token=${encodeURIComponent(token)}`;
}

async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getStoredToken();
  const headers = new Headers(init.headers);
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  if (!(init.body instanceof FormData) && !(init.body instanceof Blob) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
  });

  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      const err = await res.json();
      if (err?.detail) {
        message = typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail);
      }
    } catch {
      // ignore json parse failure
    }
    throw new Error(message);
  }

  return (await res.json()) as T;
}

export const api = {
  // Auth
  login: (username: string, password: string) =>
    apiFetch<{ access_token: string; auth_provider: string; user: User }>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  getMe: () => apiFetch<User>("/api/v1/auth/me"),
  getDemoAccounts: () => apiFetch<DemoAccount[]>("/api/v1/auth/demo-accounts"),

  // Metadata & Tickets
  getMetadata: () => apiFetch<TicketMetadata>("/api/v1/tickets/metadata"),
  listTickets: (params?: {
    status?: TicketStatus | "";
    priority?: TicketPriority | "";
    mine?: boolean;
    unassigned_only?: boolean;
    sla_breached?: boolean;
    q?: string;
    limit?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.status) qs.set("status", params.status);
    if (params?.priority) qs.set("priority", params.priority);
    if (params?.mine) qs.set("mine", "true");
    if (params?.unassigned_only) qs.set("unassigned_only", "true");
    if (params?.sla_breached !== undefined) qs.set("sla_breached", String(params.sla_breached));
    if (params?.q) qs.set("q", params.q);
    if (params?.limit) qs.set("limit", String(params.limit));
    const query = qs.toString() ? `?${qs.toString()}` : "";
    return apiFetch<{ items: Ticket[]; total: number }>(`/api/v1/tickets${query}`);
  },
  getTicket: (ticketId: string) => apiFetch<TicketDetail>(`/api/v1/tickets/${ticketId}`),
  createTicket: (payload: {
    title: string;
    description: string;
    category_id?: string | null;
    priority?: TicketPriority;
    asset_code?: string;
    ultraview_id?: string;
    ultraview_pass?: string;
    attachment_ids?: string[];
  }) =>
    apiFetch<TicketDetail>("/api/v1/tickets", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  requestUltraView: (ticketId: string) =>
    apiFetch<TicketDetail>(`/api/v1/tickets/${ticketId}/ultraview/request`, {
      method: "POST",
    }),
  provideUltraView: (ticketId: string, ultraview_id: string, ultraview_pass: string) =>
    apiFetch<TicketDetail>(`/api/v1/tickets/${ticketId}/ultraview/provide`, {
      method: "POST",
      body: JSON.stringify({ ultraview_id, ultraview_pass }),
    }),
  claimTicket: (ticketId: string) =>
    apiFetch<TicketDetail>(`/api/v1/tickets/${ticketId}/claim`, { method: "POST" }),
  assignTicket: (
    ticketId: string,
    payload: { assignee_id?: string | null; support_group_id?: string | null }
  ) =>
    apiFetch<TicketDetail>(`/api/v1/tickets/${ticketId}/assign`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateTicketStatus: (ticketId: string, status: TicketStatus, note?: string) =>
    apiFetch<TicketDetail>(`/api/v1/tickets/${ticketId}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status, note }),
    }),
  updateTicketPriority: (ticketId: string, priority: TicketPriority) =>
    apiFetch<TicketDetail>(`/api/v1/tickets/${ticketId}/priority`, {
      method: "PATCH",
      body: JSON.stringify({ priority }),
    }),
  rateTicket: (ticketId: string, rating: number, feedback?: string, close_ticket = true) =>
    apiFetch<TicketDetail>(`/api/v1/tickets/${ticketId}/rate`, {
      method: "POST",
      body: JSON.stringify({ rating, feedback, close_ticket }),
    }),

  // Comments
  addComment: (
    ticketId: string,
    payload: { body: string; is_internal: boolean; attachment_ids?: string[] }
  ) =>
    apiFetch<TicketComment>(`/api/v1/tickets/${ticketId}/comments`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  // Attachments (Presigned / Direct binary upload for Ctrl+V)
  uploadAttachment: async (
    file: File | Blob,
    fileName: string,
    ticketId?: string,
    kbArticleId?: string
  ): Promise<Attachment> => {
    const contentType = file.type || "image/png";
    const presigned = await apiFetch<{
      attachment_id: string;
      direct_upload_url: string;
    }>("/api/v1/attachments/presigned-upload", {
      method: "POST",
      body: JSON.stringify({
        file_name: fileName,
        content_type: contentType,
        size_bytes: file.size,
        ticket_id: ticketId ?? null,
        kb_article_id: kbArticleId ?? null,
      }),
    });

    const token = getStoredToken();
    const res = await fetch(`${API_BASE}${presigned.direct_upload_url}`, {
      method: "PUT",
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        "Content-Type": contentType,
      },
      body: file,
    });
    if (!res.ok) {
      throw new Error(`Upload ảnh thất bại (HTTP ${res.status})`);
    }
    return (await res.json()) as Attachment;
  },

  // Analytics & Admin
  getAnalyticsSummary: (params?: {
    date_from?: string;
    date_to?: string;
    support_group_id?: string;
    priority?: TicketPriority | "";
  }) => {
    const qs = new URLSearchParams();
    if (params?.date_from) qs.set("date_from", params.date_from);
    if (params?.date_to) qs.set("date_to", params.date_to);
    if (params?.support_group_id) qs.set("support_group_id", params.support_group_id);
    if (params?.priority) qs.set("priority", params.priority);
    const query = qs.toString() ? `?${qs.toString()}` : "";
    return apiFetch<AnalyticsSummary>(`/api/v1/analytics/summary${query}`);
  },
  exportAnalyticsReport: async (
    format: "csv" | "xlsx" | "json",
    params?: {
      date_from?: string;
      date_to?: string;
      support_group_id?: string;
      priority?: TicketPriority | "";
    }
  ): Promise<void> => {
    const qs = new URLSearchParams({ format });
    if (params?.date_from) qs.set("date_from", params.date_from);
    if (params?.date_to) qs.set("date_to", params.date_to);
    if (params?.support_group_id) qs.set("support_group_id", params.support_group_id);
    if (params?.priority) qs.set("priority", params.priority);

    const token = getStoredToken();
    const res = await fetch(`${API_BASE}/api/v1/analytics/export?${qs.toString()}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) {
      throw new Error(`Export thất bại (HTTP ${res.status})`);
    }
    const blob = await res.blob();
    const disposition = res.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename="([^"]+)"/);
    const filename = match ? match[1] : `helpdesk-report.${format}`;

    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  },
  adminListCategories: () => apiFetch<Category[]>("/api/v1/admin/categories"),
  adminCreateCategory: (payload: {
    name: string;
    slug: string;
    description?: string;
    default_group_id?: string | null;
    default_priority: TicketPriority;
  }) =>
    apiFetch<Category>("/api/v1/admin/categories", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  adminListGroups: () => apiFetch<SupportGroup[]>("/api/v1/admin/support-groups"),
  adminListSlaPolicies: () => apiFetch<SlaPolicy[]>("/api/v1/admin/sla-policies"),
  adminUpdateSlaPolicy: (
    policyId: string,
    payload: { first_response_minutes?: number; resolution_minutes?: number }
  ) =>
    apiFetch<SlaPolicy>(`/api/v1/admin/sla-policies/${policyId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  adminListUsers: () => apiFetch<User[]>("/api/v1/admin/users"),
  adminUpdateUserRole: (userId: string, role: UserRole) =>
    apiFetch<User>(`/api/v1/admin/users/${userId}`, {
      method: "PATCH",
      body: JSON.stringify({ role }),
    }),
  adminListOutboxEvents: () => apiFetch<OutboxEvent[]>("/api/v1/admin/outbox-events?limit=50"),
  adminRetryOutboxEvent: (eventId: string) =>
    apiFetch<OutboxEvent>(`/api/v1/admin/outbox-events/${eventId}/retry`, { method: "POST" }),
  adminAddKbArticle: (
    categoryId: string,
    payload: { title: string; keywords: string[]; steps: string[] }
  ) =>
    apiFetch<Category>(`/api/v1/admin/categories/${categoryId}/kb`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  adminDeleteKbArticle: (categoryId: string, articleId: string) =>
    apiFetch<Category>(`/api/v1/admin/categories/${categoryId}/kb/${articleId}`, {
      method: "DELETE",
    }),
  adminGetAutomationSettings: () =>
    apiFetch<AutomationSettings>("/api/v1/admin/automation-settings"),
  adminUpdateAutomationSettings: (payload: Partial<AutomationSettings>) =>
    apiFetch<AutomationSettings>("/api/v1/admin/automation-settings", {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  // Knowledge Base (Dedicated DB Table + Image Attachments)
  listKbArticles: (params?: {
    q?: string;
    category_id?: string;
    visibility?: KbVisibility | "";
  }) => {
    const qs = new URLSearchParams();
    if (params?.q) qs.set("q", params.q);
    if (params?.category_id) qs.set("category_id", params.category_id);
    if (params?.visibility) qs.set("visibility", params.visibility);
    const query = qs.toString() ? `?${qs.toString()}` : "";
    return apiFetch<{ items: KbArticleDetail[]; total: number }>(`/api/v1/kb${query}`);
  },
  getKbArticle: (articleId: string) =>
    apiFetch<KbArticleDetail>(`/api/v1/kb/${articleId}`),
  createKbArticle: (payload: {
    title: string;
    category_id?: string | null;
    visibility: KbVisibility;
    symptoms?: string | null;
    root_cause?: string | null;
    steps: string[];
    notes?: string | null;
    keywords: string[];
    source_ticket_id?: string | null;
    attachment_ids?: string[];
  }) =>
    apiFetch<KbArticleDetail>("/api/v1/kb", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateKbArticle: (
    articleId: string,
    payload: {
      title?: string;
      category_id?: string | null;
      visibility?: KbVisibility;
      symptoms?: string | null;
      root_cause?: string | null;
      steps?: string[];
      notes?: string | null;
      keywords?: string[];
      source_ticket_id?: string | null;
      attachment_ids?: string[];
    }
  ) =>
    apiFetch<KbArticleDetail>(`/api/v1/kb/${articleId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  deleteKbArticle: (articleId: string) =>
    apiFetch<void>(`/api/v1/kb/${articleId}`, { method: "DELETE" }),

  adminRunAutoCloseNow: (hours?: number) =>
    apiFetch<{ auto_closed: number }>(
      `/api/v1/admin/automation/run-auto-close${hours ? `?hours=${hours}` : ""}`,
      { method: "POST" }
    ),
};
