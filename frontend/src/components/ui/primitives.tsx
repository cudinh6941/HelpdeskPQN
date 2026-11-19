"use client";

import React, { useEffect, useState } from "react";
import {
  ArrowUpFromLine,
  Bug,
  Check,
  Cpu,
  HardDrive,
  Laptop,
  Network,
  Printer,
  Shield,
  Tag,
} from "lucide-react";

import { cn } from "@/lib/cn";
import { formatSlaCountdown, getInitials, STATUS_LABELS } from "@/lib/formatters";
import { Ticket, TicketPriority, TicketStatus } from "@/lib/types";

/* ===== Button (§7) ===== */
interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "outline" | "ghost" | "note" | "destructive" | "icon";
  size?: "sm" | "md";
}

export function Button({
  variant = "primary",
  size = "md",
  className,
  children,
  ...props
}: ButtonProps) {
  const variantClasses: Record<NonNullable<ButtonProps["variant"]>, string> = {
    primary: "bg-primary text-primary-foreground hover:opacity-90",
    outline: "bg-card text-foreground border border-border hover:bg-muted",
    ghost: "bg-transparent text-muted-foreground hover:bg-muted hover:text-foreground",
    note: "bg-note-ink text-primary-foreground hover:opacity-90",
    destructive: "bg-destructive text-destructive-foreground hover:opacity-90",
    icon: "size-7 p-0 rounded-sm bg-transparent text-muted-foreground hover:bg-muted hover:text-foreground",
  };

  const sizeClasses =
    variant === "icon"
      ? ""
      : size === "sm"
      ? "h-7 px-2.5 text-[13px]"
      : "h-8 md:h-8 min-h-[32px] px-3 text-[13px]";

  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-1.5 rounded-sm font-medium transition-[background-color,border-color,color,opacity,transform] duration-100 ease-out active:translate-y-[0.5px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:bg-muted disabled:text-faint disabled:border-border disabled:cursor-not-allowed disabled:active:translate-y-0 whitespace-nowrap",
        variantClasses[variant],
        sizeClasses,
        className
      )}
      {...props}
    >
      {children}
    </button>
  );
}

/* ===== Checkbox (§4.2, §7) ===== */
export function Checkbox({
  checked,
  onChange,
  ariaLabel,
  className,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  ariaLabel?: string;
  className?: string;
}) {
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={checked}
      aria-label={ariaLabel || "Select row"}
      data-checked={checked}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onChange(!checked);
      }}
      className={cn(
        "size-4 shrink-0 rounded-xs border border-input bg-card inline-flex items-center justify-center transition-[background-color,border-color,transform] duration-100 active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        checked && "bg-foreground border-foreground text-primary-foreground",
        className
      )}
    >
      {checked && <Check className="size-3" strokeWidth={2.5} />}
    </button>
  );
}

/* ===== Input / Textarea / Select (§7) ===== */
export const inputBaseClass =
  "w-full rounded-md border border-input bg-card px-3 py-1.5 text-[15px] leading-[22px] text-foreground placeholder:text-faint focus:outline-none focus:border-foreground/30 focus:ring-2 focus:ring-ring/20";

export const selectBaseClass =
  "h-8 rounded-md border border-input bg-card px-2.5 text-[13px] text-foreground focus:outline-none focus:border-foreground/30 focus:ring-2 focus:ring-ring/20";

/* ===== SLA Badge (§5.1) ===== */
export function SlaBadge({
  ticket,
}: {
  ticket: Pick<
    Ticket,
    "id" | "status" | "sla_status" | "is_resolution_breached" | "resolution_due_at"
  >;
}) {
  const initialRemaining = ticket.sla_status?.remaining_seconds ?? null;
  const [liveRemaining, setLiveRemaining] = useState<number | null>(initialRemaining);

  useEffect(() => {
    setLiveRemaining(ticket.sla_status?.remaining_seconds ?? null);
  }, [ticket.sla_status?.remaining_seconds, ticket.id]);

  const rawState = ticket.sla_status?.state;
  const isCancelled = ticket.status === "CANCELLED";
  const isTerminal =
    ticket.status === "RESOLVED" || ticket.status === "CLOSED";
  const isPaused = rawState === "PAUSED" || ticket.status === "WAITING_FOR_USER";

  useEffect(() => {
    if (isCancelled || isTerminal || isPaused || liveRemaining === null) return;
    const intervalMs = Math.abs(liveRemaining) < 3600 ? 1000 : 60000;
    const timer = window.setInterval(() => {
      setLiveRemaining((prev) => (prev !== null ? prev - Math.floor(intervalMs / 1000) : null));
    }, intervalMs);
    return () => window.clearInterval(timer);
  }, [isCancelled, isTerminal, isPaused, liveRemaining]);

  let visualState: "urgent" | "neutral" | "breached" | "paused" | "met" | "cancelled" = "neutral";
  if (isCancelled) {
    visualState = "cancelled";
  } else if (isTerminal) {
    visualState = ticket.is_resolution_breached ? "breached" : "met";
  } else if (isPaused) {
    visualState = "paused";
  } else if (
    rawState === "BREACHED" ||
    ticket.is_resolution_breached ||
    (liveRemaining !== null && liveRemaining <= 0)
  ) {
    visualState = "breached";
  } else if (
    rawState === "WARNING" ||
    (liveRemaining !== null && liveRemaining < 1800)
  ) {
    visualState = "urgent";
  }

  const label = formatSlaCountdown(liveRemaining, visualState);

  const badgeColors: Record<typeof visualState, string> = {
    urgent: "bg-sla-urgent text-sla-urgent-fg",
    neutral: "bg-sla-neutral text-sla-neutral-fg",
    breached: "bg-sla-breached text-sla-breached-fg",
    paused: "bg-sla-neutral text-sla-neutral-fg",
    met: "bg-sla-neutral text-sla-neutral-fg",
    cancelled: "bg-muted text-muted-foreground",
  };

  return (
    <span
      aria-label={`SLA ${label}`}
      className={cn(
        "inline-flex h-6 items-center rounded-sm px-2 text-[13px] font-medium leading-4 tabular-nums whitespace-nowrap",
        badgeColors[visualState]
      )}
    >
      {label}
    </span>
  );
}

/* ===== Status Badge ===== */
const STATUS_STYLES: Record<TicketStatus, { pill: string; dot: string }> = {
  NEW: {
    pill: "border-border bg-card text-foreground",
    dot: "bg-[#3B6FE0]",
  },
  ASSIGNED: {
    pill: "border-border bg-card text-foreground",
    dot: "bg-[#0F9D8A]",
  },
  IN_PROGRESS: {
    pill: "border-[#D5E2FA] bg-[#F5F8FF] text-[#1E3A8A]",
    dot: "bg-[#3B6FE0]",
  },
  WAITING_FOR_USER: {
    pill: "border-note-border bg-note text-note-ink",
    dot: "bg-[#D97706]",
  },
  REOPENED: {
    pill: "border-[#F3D9B1] bg-[#FFF8EE] text-[#7C4A03]",
    dot: "bg-[#EE9B3B]",
  },
  RESOLVED: {
    pill: "border-[#CBEBD9] bg-[#F1FAF5] text-[#14532D]",
    dot: "bg-[#1F9D68]",
  },
  CLOSED: {
    pill: "border-border bg-muted/70 text-muted-foreground",
    dot: "bg-faint",
  },
  CANCELLED: {
    pill: "border-border bg-muted/70 text-muted-foreground",
    dot: "bg-faint",
  },
};

export function StatusBadge({ status }: { status: TicketStatus }) {
  const style = STATUS_STYLES[status];
  return (
    <span
      className={cn(
        "inline-flex h-6 items-center gap-1.5 rounded-sm border px-2 text-[13px] font-medium leading-4 whitespace-nowrap shrink-0",
        style.pill
      )}
    >
      <span aria-hidden className={cn("size-1.5 rounded-full shrink-0", style.dot)} />
      <span>{STATUS_LABELS[status]}</span>
    </span>
  );
}

/* ===== Topic Badge (§5.3) ===== */
function getTopicIcon(slug?: string | null) {
  const s = (slug || "").toLowerCase();
  if (s.includes("network") || s.includes("wifi") || s.includes("vpn")) {
    return <Network className="size-3.5 text-[#3B6FE0] shrink-0" strokeWidth={1.5} />;
  }
  if (s.includes("printer")) {
    return <Printer className="size-3.5 text-[#0F9D8A] shrink-0" strokeWidth={1.5} />;
  }
  if (s.includes("pc") || s.includes("laptop") || s.includes("hardware")) {
    return <Laptop className="size-3.5 text-[#0F9D8A] shrink-0" strokeWidth={1.5} />;
  }
  if (s.includes("account") || s.includes("ad")) {
    return <Shield className="size-3.5 text-[#6E56CF] shrink-0" strokeWidth={1.5} />;
  }
  if (s.includes("erp")) {
    return <Bug className="size-3.5 text-[#D97706] shrink-0" strokeWidth={1.5} />;
  }
  if (s.includes("request")) {
    return <ArrowUpFromLine className="size-3.5 text-[#2563EB] shrink-0" strokeWidth={1.5} />;
  }
  if (s.includes("asset")) {
    return <HardDrive className="size-3.5 text-muted-foreground shrink-0" strokeWidth={1.5} />;
  }
  return <Cpu className="size-3.5 text-muted-foreground shrink-0" strokeWidth={1.5} />;
}

export function TopicBadge({
  label,
  iconSlug,
  mono = false,
}: {
  label: string;
  iconSlug?: string | null;
  mono?: boolean;
}) {
  const isAsset = iconSlug === "asset";
  return (
    <span
      className={cn(
        "inline-flex h-6 items-center gap-1.5 rounded-sm border border-border px-2 text-[13px] font-normal leading-4 text-foreground whitespace-nowrap shrink-0",
        isAsset ? "bg-muted/50" : "bg-card"
      )}
    >
      {iconSlug === "tag" ? (
        <Tag className="size-3.5 text-muted-foreground shrink-0" strokeWidth={1.5} />
      ) : (
        getTopicIcon(iconSlug)
      )}
      <span className={mono ? "font-mono text-[12px] tabular-nums" : ""}>{label}</span>
    </span>
  );
}

/* ===== Priority Glyph (§4.1) ===== */
export function PriorityGlyph({ priority }: { priority: TicketPriority }) {
  const colorClass =
    priority === "CRITICAL"
      ? "text-destructive"
      : priority === "HIGH"
      ? "text-[var(--priority-high)]"
      : "text-faint";

  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden
      className={cn("size-4 shrink-0", colorClass)}
    >
      <rect x="2" y="3.5" width="12" height="1.6" rx="0.8" fill="currentColor" />
      <rect x="2" y="7.2" width="9" height="1.6" rx="0.8" fill="currentColor" />
      <rect x="2" y="10.9" width="6" height="1.6" rx="0.8" fill="currentColor" />
    </svg>
  );
}

/* ===== Avatar & Company Logo (§4.2, §7) ===== */
export function Avatar({ name }: { name?: string | null }) {
  return (
    <span className="size-6 rounded-full bg-muted text-foreground text-[11px] font-medium inline-flex items-center justify-center shrink-0 select-none">
      {getInitials(name)}
    </span>
  );
}

export function CompanyLogo({ name }: { name?: string | null }) {
  const letter = (name || "IT").trim().slice(0, 2);
  return (
    <span className="size-6 rounded-sm bg-muted border border-border text-foreground text-[11px] font-medium inline-flex items-center justify-center shrink-0 select-none">
      {letter}
    </span>
  );
}

/* ===== GPU Sheen Skeleton (§12) ===== */
export function SkeletonRow({
  count = 4,
  compact = false,
}: {
  count?: number;
  compact?: boolean;
}) {
  return (
    <div>
      {Array.from({ length: count }).map((_, idx) => (
        <div
          key={idx}
          className={cn(
            "border-b border-border-subtle last:border-b-0 px-4 py-3 flex items-center gap-4",
            compact ? "min-h-[60px]" : "h-[72px]"
          )}
        >
          {!compact && <div className="size-4 rounded-xs skeleton-sheen shrink-0" />}
          <div className="w-[88px] h-6 rounded-xs skeleton-sheen shrink-0" />
          <div className="flex-1 space-y-2">
            <div className="h-4 w-2/5 rounded-xs skeleton-sheen" />
            <div className="h-4 w-3/5 rounded-xs skeleton-sheen" />
          </div>
        </div>
      ))}
    </div>
  );
}
