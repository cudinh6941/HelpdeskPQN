"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronDown, ChevronRight, Inbox, Search, UserCheck } from "lucide-react";

import { AppShell } from "@/components/AppShell";
import { useNavigationProgress } from "@/components/NavigationProgress";
import { QueueRow } from "@/components/QueueRow";
import { Button, PriorityGlyph, SkeletonRow } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { cn } from "@/lib/cn";
import { isItRole, PRIORITY_LABELS } from "@/lib/formatters";
import { Ticket, TicketPriority } from "@/lib/types";
import { useRealtime } from "@/lib/use-realtime";

type QueueFilter = "ALL" | "NEW" | "MINE" | "WAITING" | "BREACHED";

const PRIORITY_ORDER: TicketPriority[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];

export default function WorkspaceQueuePage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const { startNavigation } = useNavigationProgress();

  const [filter, setFilter] = useState<QueueFilter>("ALL");
  const [search, setSearch] = useState("");
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [checkedIds, setCheckedIds] = useState<Set<string>>(new Set());
  const [collapsedGroups, setCollapsedGroups] = useState<Set<TicketPriority>>(new Set());
  const [focusedIndex, setFocusedIndex] = useState<number>(-1);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [highlightedIds, setHighlightedIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!authLoading && user && !isItRole(user.role)) {
      router.replace("/portal");
    }
  }, [authLoading, user, router]);

  const loadTickets = useCallback(
    async (silent = false) => {
      if (!silent) setLoading(true);
      setError(null);
      try {
        const params: Parameters<typeof api.listTickets>[0] = {
          limit: 150,
          q: search.trim() || undefined,
        };
        if (filter === "NEW") params.status = "NEW";
        else if (filter === "MINE") params.mine = true;
        else if (filter === "WAITING") params.status = "WAITING_FOR_USER";
        else if (filter === "BREACHED") params.sla_breached = true;

        const res = await api.listTickets(params);
        setTickets(res.items);
        if (!silent) {
          setFocusedIndex(res.items.length > 0 ? 0 : -1);
        }
      } catch (err: unknown) {
        if (!silent) {
          setError(
            err instanceof Error
              ? err.message
              : "Không thể tải danh sách ticket. Kiểm tra kết nối backend rồi thử lại."
          );
        }
      } finally {
        if (!silent) setLoading(false);
      }
    },
    [filter, search]
  );

  useEffect(() => {
    if (user && isItRole(user.role)) {
      void loadTickets(false);
    }
  }, [user, loadTickets]);

  useRealtime((evt) => {
    if (user && isItRole(user.role)) {
      void loadTickets(true);
      if (evt.type === "TICKET_CREATED" && evt.ticket_id) {
        setHighlightedIds((prev) => new Set(prev).add(evt.ticket_id));
        window.setTimeout(() => {
          setHighlightedIds((prev) => {
            const next = new Set(prev);
            next.delete(evt.ticket_id);
            return next;
          });
        }, 1200);
      }
    }
  });

  const groupedTickets = useMemo(() => {
    const map: Record<TicketPriority, Ticket[]> = {
      CRITICAL: [],
      HIGH: [],
      MEDIUM: [],
      LOW: [],
    };
    for (const t of tickets) {
      map[t.priority].push(t);
    }
    return map;
  }, [tickets]);

  const flatVisibleTickets = useMemo(() => {
    const list: Ticket[] = [];
    for (const p of PRIORITY_ORDER) {
      if (!collapsedGroups.has(p)) {
        list.push(...groupedTickets[p]);
      }
    }
    return list;
  }, [groupedTickets, collapsedGroups]);

  const toggleCheck = (id: string, next: boolean) => {
    setCheckedIds((prev) => {
      const copy = new Set(prev);
      if (next) copy.add(id);
      else copy.delete(id);
      return copy;
    });
  };

  const toggleGroup = (priority: TicketPriority) => {
    setCollapsedGroups((prev) => {
      const copy = new Set(prev);
      if (copy.has(priority)) copy.delete(priority);
      else copy.add(priority);
      return copy;
    });
  };

  const handleBulkAssignToMe = async () => {
    if (checkedIds.size === 0) return;
    setBulkBusy(true);
    try {
      await Promise.all(Array.from(checkedIds).map((id) => api.claimTicket(id)));
      setCheckedIds(new Set());
      await loadTickets();
    } finally {
      setBulkBusy(false);
    }
  };

  // Keyboard navigation (§13): ArrowUp/ArrowDown, Space, Enter, E (Assign to me)
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.tagName === "SELECT")
      ) {
        return;
      }
      if (!flatVisibleTickets.length) return;

      if (e.key === "ArrowDown") {
        e.preventDefault();
        setFocusedIndex((prev) => Math.min(flatVisibleTickets.length - 1, prev + 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setFocusedIndex((prev) => Math.max(0, prev - 1));
      } else if (e.key === " " && focusedIndex >= 0) {
        e.preventDefault();
        const t = flatVisibleTickets[focusedIndex];
        if (t) toggleCheck(t.id, !checkedIds.has(t.id));
      } else if (e.key === "Enter" && focusedIndex >= 0) {
        e.preventDefault();
        const t = flatVisibleTickets[focusedIndex];
        if (t) {
          const target = `/workspace/tickets/${t.id}`;
          startNavigation(target);
          router.push(target);
        }
      } else if (e.key.toLowerCase() === "e" && focusedIndex >= 0) {
        e.preventDefault();
        const t = flatVisibleTickets[focusedIndex];
        if (t) {
          void api.claimTicket(t.id).then(() => loadTickets());
        }
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [flatVisibleTickets, focusedIndex, checkedIds, router, loadTickets, startNavigation]);

  const filters: Array<{ id: QueueFilter; label: string }> = [
    { id: "ALL", label: "All" },
    { id: "NEW", label: "Unassigned" },
    { id: "MINE", label: "Assigned to me" },
    { id: "WAITING", label: "Waiting on user" },
    { id: "BREACHED", label: "SLA breached" },
  ];

  let runningRowIdx = 0;

  return (
    <AppShell>
      <div className="space-y-3">
        {/* Compact Toolbar */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-1">
            {filters.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setFilter(item.id)}
                className={cn(
                  "h-8 px-3 rounded-sm text-[13px] font-medium border transition-colors duration-75",
                  filter === item.id
                    ? "bg-card text-foreground border-border"
                    : "bg-transparent text-muted-foreground border-transparent hover:bg-muted/60 hover:text-foreground"
                )}
              >
                {item.label}
              </button>
            ))}

            {checkedIds.size > 0 && (
              <Button
                variant="outline"
                disabled={bulkBusy}
                onClick={() => void handleBulkAssignToMe()}
                className="ml-2"
              >
                <UserCheck className="size-3.5" strokeWidth={1.5} />
                <span>Assign to me ({checkedIds.size})</span>
              </Button>
            )}
          </div>

          <div className="relative w-full sm:w-72">
            <Search
              className="size-4 text-faint absolute left-2.5 top-2"
              strokeWidth={1.5}
            />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Filter by code, asset, title..."
              className="w-full h-8 pl-8 pr-3 rounded-md border border-input bg-card text-[13px] text-foreground placeholder:text-faint focus:outline-none focus:border-foreground/30 focus:ring-2 focus:ring-ring/20"
            />
          </div>
        </div>

        {error && (
          <div className="rounded-md border border-destructive/30 bg-destructive/5 px-4 py-2.5 text-[13px] text-destructive">
            {error}
          </div>
        )}

        {/* Queue Table Card */}
        <div
          role="grid"
          aria-label="Ticket queue"
          className="rounded-lg border border-border bg-card overflow-hidden"
        >
          {/* Column Headers (height 32px) */}
          <div className="hidden md:grid grid-cols-[16px_16px_88px_minmax(220px,1fr)_minmax(260px,1.4fr)] items-center gap-x-4 h-8 px-4 border-b border-border-subtle text-meta bg-card">
            <span />
            <span />
            <span>SLA</span>
            <span>Requester</span>
            <span>Topic</span>
          </div>

          {loading ? (
            <SkeletonRow count={5} />
          ) : tickets.length === 0 ? (
            <div className="px-4 py-8 flex flex-col items-start gap-3">
              <Inbox className="size-5 text-faint" strokeWidth={1.5} />
              <p className="text-body">
                No tickets match the current filter. Switch back to All to inspect the full queue.
              </p>
              {filter !== "ALL" && (
                <Button variant="outline" onClick={() => setFilter("ALL")}>
                  View all tickets
                </Button>
              )}
            </div>
          ) : (
            <div>
              {PRIORITY_ORDER.map((priority) => {
                const groupRows = groupedTickets[priority];
                if (!groupRows.length) return null;
                const isCollapsed = collapsedGroups.has(priority);

                return (
                  <div key={priority}>
                    {/* Priority Group Header (44px) */}
                    <button
                      type="button"
                      onClick={() => toggleGroup(priority)}
                      className="group w-full h-11 px-4 flex items-center justify-between border-b border-border-subtle bg-background text-left hover:bg-muted/60 transition-colors duration-75"
                    >
                      <div className="flex items-center gap-2">
                        <PriorityGlyph priority={priority} />
                        <span className="text-body-strong">
                          {PRIORITY_LABELS[priority]}
                        </span>
                        <span className="text-body text-muted-foreground tabular-nums">
                          {groupRows.length}
                        </span>
                      </div>
                      <span className="text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity duration-75">
                        {isCollapsed ? (
                          <ChevronRight className="size-4" strokeWidth={1.5} />
                        ) : (
                          <ChevronDown className="size-4" strokeWidth={1.5} />
                        )}
                      </span>
                    </button>

                    {!isCollapsed &&
                      groupRows.map((ticket) => {
                        const rowIdx = runningRowIdx++;
                        return (
                          <QueueRow
                            key={ticket.id}
                            ticket={ticket}
                            rowIndex={rowIdx}
                            focused={rowIdx === focusedIndex}
                            highlighted={highlightedIds.has(ticket.id)}
                            checked={checkedIds.has(ticket.id)}
                            onCheckChange={(next) => toggleCheck(ticket.id, next)}
                            onClick={() => {
                              const target = `/workspace/tickets/${ticket.id}`;
                              startNavigation(target);
                              router.push(target);
                            }}
                            layout="wide"
                          />
                        );
                      })}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
