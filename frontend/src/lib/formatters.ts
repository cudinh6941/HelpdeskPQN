import { Ticket, TicketPriority, TicketStatus, UserRole } from "./types";

export const STATUS_LABELS: Record<TicketStatus, string> = {
  NEW: "New",
  ASSIGNED: "Assigned",
  IN_PROGRESS: "In progress",
  WAITING_FOR_USER: "Waiting on user",
  RESOLVED: "Resolved",
  CLOSED: "Closed",
  REOPENED: "Reopened",
  CANCELLED: "Cancelled",
};

export const PRIORITY_LABELS: Record<TicketPriority, string> = {
  CRITICAL: "Urgent",
  HIGH: "High",
  MEDIUM: "Medium",
  LOW: "Low",
};

export const ROLE_LABELS: Record<UserRole, string> = {
  END_USER: "Nhân viên",
  IT_AGENT: "Kỹ thuật viên",
  IT_LEAD: "Trưởng nhóm IT",
  SYS_ADMIN: "Quản trị viên",
};

export function getDepartmentLabel(ticket: Ticket): string {
  if (ticket.support_group?.name) return ticket.support_group.name;
  if (ticket.category?.name) return ticket.category.name;
  return "Internal IT";
}

export function formatDateTime(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatRelativeTime(iso?: string | null): string {
  if (!iso) return "—";
  const diffSec = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (diffSec < 45) return "Just now";
  const mins = Math.floor(diffSec / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

export function formatSlaCountdown(
  remainingSeconds: number | null | undefined,
  state: "urgent" | "neutral" | "breached" | "paused" | "met" | "cancelled"
): string {
  if (state === "cancelled") return "Cancelled";
  if (state === "paused") return "Paused";
  if (state === "met") return "Met";
  if (remainingSeconds === null || remainingSeconds === undefined) return "—";

  if (state === "breached" || remainingSeconds <= 0) {
    const overdueMins = Math.max(1, Math.floor(Math.abs(remainingSeconds) / 60));
    return overdueMins > 999 ? "Overdue" : `-${overdueMins}m`;
  }

  const totalSec = Math.floor(remainingSeconds);
  if (totalSec < 3600) {
    const mins = Math.floor(totalSec / 60);
    const secs = totalSec % 60;
    return `${mins}m ${String(secs).padStart(2, "0")}s`;
  }

  const hrs = Math.floor(totalSec / 3600);
  const remMins = Math.floor((totalSec % 3600) / 60);
  return `${hrs}h ${String(remMins).padStart(2, "0")}m`;
}

export function formatDurationCompact(seconds?: number | null): string {
  if (seconds === null || seconds === undefined || seconds === 0) return "0m";
  const mins = Math.floor(Math.abs(seconds) / 60);
  const hrs = Math.floor(mins / 60);
  const remMins = mins % 60;
  if (hrs > 0) return `${hrs}h ${String(remMins).padStart(2, "0")}m`;
  return `${mins}m`;
}

export function isItRole(role?: UserRole | null): boolean {
  return role === "IT_AGENT" || role === "IT_LEAD" || role === "SYS_ADMIN";
}

export function getInitials(name?: string | null): string {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2);
  return `${parts[0][0]}${parts[parts.length - 1][0]}`;
}

export function formatUltraViewId(raw?: string | null): string {
  if (!raw) return "—";
  const digits = raw.replace(/\D/g, "");
  if (digits.length === 8) {
    return `${digits.slice(0, 2)} ${digits.slice(2, 5)} ${digits.slice(5)}`;
  }
  if (digits.length === 9) {
    return `${digits.slice(0, 3)} ${digits.slice(3, 6)} ${digits.slice(6)}`;
  }
  return digits || raw;
}

const UV_LABELED_RE =
  /(?:id|uv|ultraview(?:er)?)\s*[:=\-]?\s*(\d{2,3}[\s.\-]?\d{3}[\s.\-]?\d{3,4}|\d{8,11})\b[\s\S]{0,40}?(?:pass(?:word)?|mk|mật\s*khẩu|pw|\/|\|)\s*[:=\-]?\s*([A-Za-z0-9@#$%!]{4,12})\b/i;

const UV_PAIR_RE =
  /\b(\d{2,3}[\s.\-]?\d{3}[\s.\-]?\d{3,4}|\d{8,11})\s*[/|]\s*([A-Za-z0-9@#$%!]{4,12})\b/;

export function extractUltraViewFromText(
  text?: string | null
): { id: string; pass: string } | null {
  if (!text) return null;
  for (const re of [UV_LABELED_RE, UV_PAIR_RE]) {
    const match = text.match(re);
    if (match) {
      const id = match[1].replace(/\D/g, "");
      const pass = match[2].trim();
      if (id.length >= 8 && id.length <= 11 && pass.length >= 4 && pass.length <= 12) {
        return { id, pass };
      }
    }
  }
  return null;
}
