"use client";

import React from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Lock,
  MessageSquare,
  PlusCircle,
  Star,
  UserCheck,
} from "lucide-react";

import { formatRelativeTime } from "@/lib/formatters";
import { TimelineEvent } from "@/lib/types";

function eventIcon(type: string) {
  switch (type) {
    case "TICKET_CREATED":
      return <PlusCircle className="size-3.5 text-muted-foreground" strokeWidth={1.5} />;
    case "TICKET_CLAIMED":
    case "TICKET_ASSIGNED":
      return <UserCheck className="size-3.5 text-muted-foreground" strokeWidth={1.5} />;
    case "INTERNAL_NOTE_ADDED":
      return <Lock className="size-3.5 text-note-ink" strokeWidth={1.5} />;
    case "COMMENT_ADDED":
      return <MessageSquare className="size-3.5 text-muted-foreground" strokeWidth={1.5} />;
    case "SLA_WARNING":
    case "SLA_BREACHED":
    case "SLA_RESPONSE_BREACHED":
      return <AlertTriangle className="size-3.5 text-destructive" strokeWidth={1.5} />;
    case "TICKET_RATED":
      return <Star className="size-3.5 text-muted-foreground" strokeWidth={1.5} />;
    case "STATUS_CHANGED":
      return <CheckCircle2 className="size-3.5 text-muted-foreground" strokeWidth={1.5} />;
    default:
      return <Clock className="size-3.5 text-faint" strokeWidth={1.5} />;
  }
}

export function TicketTimeline({ events }: { events: TimelineEvent[] }) {
  if (!events.length) {
    return <p className="text-meta-faint">Chưa có sự kiện nào.</p>;
  }

  return (
    <ol className="relative border-l border-border ml-2 space-y-3">
      {events.map((ev) => {
        const isInternal = Boolean(ev.payload?.is_internal);
        const summary = ev.payload?.summary || ev.event_type;
        const actorName = ev.payload?.actor?.full_name;
        return (
          <li key={ev.id} className="ml-4">
            <span className="absolute -left-[9px] flex items-center justify-center size-[18px] rounded-full bg-card border border-border">
              {eventIcon(ev.event_type)}
            </span>
            <div className="flex flex-wrap items-center gap-1.5">
              <p className="text-[13px] leading-[18px] text-foreground">{summary}</p>
              {isInternal && (
                <span className="text-[12px] px-1.5 py-0.5 rounded-sm border border-note-border bg-note text-note-ink font-medium">
                  Internal
                </span>
              )}
            </div>
            <p className="text-[12px] text-faint mt-0.5 tabular-nums">
              {formatRelativeTime(ev.created_at)}
              {actorName ? ` / ${actorName}` : ""}
            </p>
          </li>
        );
      })}
    </ol>
  );
}
