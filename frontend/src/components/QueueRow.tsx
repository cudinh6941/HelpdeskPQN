"use client";

import React from "react";
import { CheckCircle2, Clock, CornerUpLeft } from "lucide-react";

import { cn } from "@/lib/cn";
import {
  formatRelativeTime,
  getDepartmentLabel,
  PRIORITY_LABELS,
  STATUS_LABELS,
} from "@/lib/formatters";
import { Ticket } from "@/lib/types";
import {
  Checkbox,
  CompanyLogo,
  PriorityGlyph,
  SlaBadge,
  StatusBadge,
  TopicBadge,
} from "@/components/ui/primitives";

interface QueueRowProps {
  ticket: Ticket;
  selected?: boolean;
  checked?: boolean;
  onCheckChange?: (checked: boolean) => void;
  onClick: () => void;
  layout?: "wide" | "compact";
  rowIndex?: number;
  focused?: boolean;
  highlighted?: boolean;
}

function ActionStatusGlyph({ status }: { status: Ticket["status"] }) {
  if (status === "NEW" || status === "ASSIGNED" || status === "IN_PROGRESS" || status === "REOPENED") {
    return (
      <CornerUpLeft
        className="size-4 text-[var(--action-reply)] shrink-0 mt-[3px]"
        strokeWidth={1.5}
        aria-label="Needs agent reply"
      />
    );
  }
  if (status === "WAITING_FOR_USER") {
    return (
      <Clock
        className="size-4 text-faint shrink-0 mt-[3px]"
        strokeWidth={1.5}
        aria-label="Waiting on user"
      />
    );
  }
  return (
    <CheckCircle2
      className="size-4 text-faint shrink-0 mt-[3px]"
      strokeWidth={1.5}
      aria-label={STATUS_LABELS[status]}
    />
  );
}

export function QueueRow({
  ticket,
  selected = false,
  checked = false,
  onCheckChange,
  onClick,
  layout = "wide",
  rowIndex,
  focused = false,
  highlighted = false,
}: QueueRowProps) {
  const deptLabel = getDepartmentLabel(ticket);
  const isUnread = ticket.status === "NEW";
  const isMutedTerminal =
    ticket.status === "CLOSED" || ticket.status === "CANCELLED";

  if (layout === "compact") {
    return (
      <div
        role="row"
        tabIndex={0}
        data-selected={selected}
        data-row-index={rowIndex}
        onClick={onClick}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            onClick();
          }
        }}
        className={cn(
          "cursor-pointer px-4 py-3 min-h-[72px] border-b border-border-subtle last:border-b-0 bg-card transition-colors duration-75 hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
          selected && "bg-muted border-l-2 border-l-foreground"
        )}
      >
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <ActionStatusGlyph status={ticket.status} />
            <span className="text-[13px] text-muted-foreground font-mono tabular-nums truncate">
              {ticket.ticket_code}
            </span>
          </div>
          <SlaBadge ticket={ticket} />
        </div>

        <p className="text-body-strong truncate mt-1.5">{ticket.title}</p>

        <div className="flex items-center justify-between gap-2 mt-1 text-meta truncate">
          <span className="truncate">
            <span className="text-foreground">{deptLabel}</span>
            <span className="text-muted-foreground"> / {ticket.requester.full_name}</span>
          </span>
        </div>
      </div>
    );
  }

  return (
    <div
      role="row"
      tabIndex={0}
      data-selected={selected || focused}
      data-row-index={rowIndex}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          onClick();
        }
      }}
      style={
        rowIndex !== undefined
          ? { animationDelay: `${Math.min(rowIndex, 8) * 18}ms` }
          : undefined
      }
      className={cn(
        "anim-fade-up cursor-pointer grid grid-cols-[16px_16px_88px_minmax(220px,1fr)_minmax(260px,1.4fr)] items-start gap-x-4 border-b border-border-subtle px-4 py-3 min-h-[72px] last:border-b-0 bg-card transition-colors duration-1000 hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
        isMutedTerminal && "opacity-75",
        highlighted && "bg-muted",
        (selected || focused) && "bg-muted border-l-2 border-l-foreground opacity-100"
      )}
    >
      <Checkbox
        checked={checked}
        onChange={(next) => onCheckChange?.(next)}
        ariaLabel={`Select ${ticket.ticket_code}`}
        className="mt-[3px]"
      />

      <ActionStatusGlyph status={ticket.status} />

      <div className="pt-[1px]">
        <SlaBadge ticket={ticket} />
      </div>

      {/* Requester Cell */}
      <div className="min-w-0">
        <div className="flex items-center gap-2 min-w-0">
          <CompanyLogo name={deptLabel} />
          <div className="truncate text-[15px] leading-[22px]">
            <span className={isUnread ? "font-medium text-foreground" : "font-normal text-foreground"}>
              {deptLabel}
            </span>
            <span className="text-muted-foreground"> / {ticket.requester.full_name}</span>
          </div>
        </div>
        <div className="mt-1.5 pl-8 flex items-center gap-1.5 text-meta">
          <PriorityGlyph priority={ticket.priority} />
          <span>{PRIORITY_LABELS[ticket.priority]}</span>
          <span className="text-faint" aria-hidden>·</span>
          <span className="text-meta-faint tabular-nums">
            {formatRelativeTime(ticket.updated_at || ticket.created_at)}
          </span>
        </div>
      </div>

      {/* Topic Cell */}
      <div className="min-w-0">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-meta font-mono tabular-nums shrink-0">
            {ticket.ticket_code}
          </span>
          <span className="text-body-strong truncate">{ticket.title}</span>
        </div>
        <div className="mt-1.5 flex items-center gap-2 overflow-hidden">
          <StatusBadge status={ticket.status} />
          {ticket.category && (
            <TopicBadge
              label={ticket.category.name}
              iconSlug={ticket.category.slug}
            />
          )}
          {ticket.asset_code && (
            <TopicBadge
              label={ticket.asset_code}
              iconSlug="asset"
              mono
            />
          )}
        </div>
      </div>
    </div>
  );
}
