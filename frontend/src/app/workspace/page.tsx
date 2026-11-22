"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Inbox,
  Plus,
  Search,
  UserCheck,
  X,
} from "lucide-react";

import { AppShell } from "@/components/AppShell";
import { useNavigationProgress } from "@/components/NavigationProgress";
import { QueueRow } from "@/components/QueueRow";
import { WalkupTicketModal } from "@/components/WalkupTicketModal";
import {
  Button,
  PriorityGlyph,
  SkeletonRow,
  selectBaseClass,
} from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { cn } from "@/lib/cn";
import { isItRole, PRIORITY_LABELS } from "@/lib/formatters";
import { Ticket, TicketMetadata, TicketPriority, TicketStatus } from "@/lib/types";
import { useRealtime } from "@/lib/use-realtime";

type QueueFilter = "ALL" | "NEW" | "MINE" | "WAITING" | "BREACHED";

const PRIORITY_ORDER: TicketPriority[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];
const PAGE_SIZE = 30;

export default function WorkspaceQueuePage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const { startNavigation } = useNavigationProgress();

  const [filter, setFilter] = useState<QueueFilter>("ALL");
  const [search, setSearch] = useState("");
  const [groupFilter, setGroupFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [assigneeFilter, setAssigneeFilter] = useState("");
  const [priorityFilter, setPriorityFilter] = useState<TicketPriority | "">("");
  const [page, setPage] = useState(0);

  const [meta, setMeta] = useState<TicketMetadata | null>(null);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [checkedIds, setCheckedIds] = useState<Set<string>>(new Set());
  const [collapsedGroups, setCollapsedGroups] = useState<Set<TicketPriority>>(new Set());
  const [focusedIndex, setFocusedIndex] = useState<number>(-1);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkNotice, setBulkNotice] = useState<string | null>(null);
  const [highlightedIds, setHighlightedIds] = useState<Set<string>>(new Set());
  const [walkupOpen, setWalkupOpen] = useState(false);

  useEffect(() => {
    if (!authLoading && user && !isItRole(user.role)) {
      router.replace("/portal");
    }
  }, [authLoading, user, router]);

  useEffect(() => {
    if (user && isItRole(user.role)) {
      void api
        .getMetadata()
        .then(setMeta)
        .catch(() => {
          // ignore transient metadata error
        });
    }
  }, [user]);

  useEffect(() => {
    setPage(0);
  }, [filter, search, groupFilter, categoryFilter, assigneeFilter, priorityFilter]);

  const loadTickets = useCallback(
    async (silent = false) => {
      if (!silent) setLoading(true);
      setError(null);
      try {
        const params: Parameters<typeof api.listTickets>[0] = {
          limit: PAGE_SIZE,
          offset: page * PAGE_SIZE,
          q: search.trim() || undefined,
          support_group_id: groupFilter || undefined,
          category_id: categoryFilter || undefined,
          assignee_id: assigneeFilter || undefined,
          priority: priorityFilter || undefined,
        };
        if (filter === "NEW") params.status = "NEW";
        else if (filter === "MINE") params.mine = true;
        else if (filter === "WAITING") params.status = "WAITING_FOR_USER";
        else if (filter === "BREACHED") params.sla_breached = true;

        const res = await api.listTickets(params);
        setTickets(res.items);
        setTotalCount(res.total);
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
    [filter, search, groupFilter, categoryFilter, assigneeFilter, priorityFilter, page]
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

  const runBulkAction = async (
    payload: Omit<Parameters<typeof api.bulkTicketAction>[0], "ticket_ids">
  ) => {
    if (checkedIds.size === 0) return;
    setBulkBusy(true);
    setBulkNotice(null);
    try {
      const res = await api.bulkTicketAction({
        ticket_ids: Array.from(checkedIds),
        ...payload,
      });
      setCheckedIds(new Set());
      setBulkNotice(
        res.skipped > 0
          ? `Updated ${res.updated} ticket(s), skipped ${res.skipped}.`
          : `Updated ${res.updated} ticket(s).`
      );
      await loadTickets(false);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Bulk update failed.");
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
          const targetUrl = `/workspace/tickets/${t.id}`;
          startNavigation(targetUrl);
          router.push(targetUrl);
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

  const hasAdvancedFilter = Boolean(
    search.trim() || groupFilter || categoryFilter || assigneeFilter || priorityFilter || filter !== "ALL"
  );

  const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));
  const rangeStart = totalCount === 0 ? 0 : page * PAGE_SIZE + 1;
  const rangeEnd = Math.min(totalCount, (page + 1) * PAGE_SIZE);

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
          </div>

          <div className="flex items-center gap-2 w-full sm:w-auto">
            <div className="relative flex-1 sm:w-72">
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

            <Button
              type="button"
              variant="primary"
              size="md"
              onClick={() => setWalkupOpen(true)}
            >
              <Plus className="size-3.5" strokeWidth={1.75} />
              <span>Walk-up</span>
            </Button>
          </div>
        </div>

        {/* Advanced Dropdown Filters */}
        {meta && (
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={groupFilter}
              onChange={(e) => setGroupFilter(e.target.value)}
              aria-label="Filter by support group"
              className={selectBaseClass}
            >
              <option value="">All groups</option>
              {meta.support_groups.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
            </select>

            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              aria-label="Filter by category"
              className={selectBaseClass}
            >
              <option value="">All categories</option>
              {meta.categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>

            <select
              value={assigneeFilter}
              onChange={(e) => setAssigneeFilter(e.target.value)}
              aria-label="Filter by assignee"
              className={selectBaseClass}
            >
              <option value="">All assignees</option>
              {meta.it_agents.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.full_name}
                </option>
              ))}
            </select>

            <select
              value={priorityFilter}
              onChange={(e) => setPriorityFilter(e.target.value as TicketPriority | "")}
              aria-label="Filter by priority"
              className={selectBaseClass}
            >
              <option value="">All priorities</option>
              <option value="CRITICAL">Urgent</option>
              <option value="HIGH">High</option>
              <option value="MEDIUM">Medium</option>
              <option value="LOW">Low</option>
            </select>

            {hasAdvancedFilter && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => {
                  setFilter("ALL");
                  setSearch("");
                  setGroupFilter("");
                  setCategoryFilter("");
                  setAssigneeFilter("");
                  setPriorityFilter("");
                }}
              >
                <X className="size-3.5" strokeWidth={1.5} />
                <span>Reset</span>
              </Button>
            )}
          </div>
        )}

        {/* Bulk Action Toolbar */}
        {checkedIds.size > 0 && (
          <div className="anim-fade-up rounded-md border border-border bg-card px-3 py-2 flex flex-wrap items-center gap-2">
            <span className="text-[13px] font-medium text-foreground tabular-nums mr-1">
              {checkedIds.size} selected
            </span>

            <Button
              variant="outline"
              size="sm"
              disabled={bulkBusy}
              onClick={() => void runBulkAction({ action: "claim" })}
            >
              <UserCheck className="size-3.5" strokeWidth={1.5} />
              <span>Assign to me</span>
            </Button>

            {meta && (
              <>
                <select
                  value=""
                  disabled={bulkBusy}
                  onChange={(e) => {
                    if (e.target.value) {
                      void runBulkAction({ action: "assign", assignee_id: e.target.value });
                    }
                  }}
                  aria-label="Bulk assign to agent"
                  className={selectBaseClass}
                >
                  <option value="">Assign to...</option>
                  {meta.it_agents.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.full_name}
                    </option>
                  ))}
                </select>

                <select
                  value=""
                  disabled={bulkBusy}
                  onChange={(e) => {
                    if (e.target.value) {
                      void runBulkAction({ action: "assign", support_group_id: e.target.value });
                    }
                  }}
                  aria-label="Bulk move support group"
                  className={selectBaseClass}
                >
                  <option value="">Move group...</option>
                  {meta.support_groups.map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.name}
                    </option>
                  ))}
                </select>
              </>
            )}

            <select
              value=""
              disabled={bulkBusy}
              onChange={(e) => {
                if (e.target.value) {
                  void runBulkAction({
                    action: "status",
                    status: e.target.value as TicketStatus,
                  });
                }
              }}
              aria-label="Bulk update status"
              className={selectBaseClass}
            >
              <option value="">Set status...</option>
              <option value="IN_PROGRESS">In Progress</option>
              <option value="WAITING_FOR_USER">Waiting on user</option>
              <option value="RESOLVED">Resolved</option>
              <option value="CLOSED">Closed</option>
            </select>

            <select
              value=""
              disabled={bulkBusy}
              onChange={(e) => {
                if (e.target.value) {
                  void runBulkAction({
                    action: "priority",
                    priority: e.target.value as TicketPriority,
                  });
                }
              }}
              aria-label="Bulk update priority"
              className={selectBaseClass}
            >
              <option value="">Set priority...</option>
              <option value="CRITICAL">Urgent</option>
              <option value="HIGH">High</option>
              <option value="MEDIUM">Medium</option>
              <option value="LOW">Low</option>
            </select>

            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setCheckedIds(new Set())}
            >
              Clear
            </Button>
          </div>
        )}

        {bulkNotice && (
          <div className="rounded-md border border-border bg-card px-3.5 py-2 text-[13px] text-foreground flex items-center justify-between">
            <span>{bulkNotice}</span>
            <button
              type="button"
              onClick={() => setBulkNotice(null)}
              className="text-faint hover:text-foreground"
            >
              <X className="size-3.5" />
            </button>
          </div>
        )}

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
              {hasAdvancedFilter && (
                <Button
                  variant="outline"
                  onClick={() => {
                    setFilter("ALL");
                    setSearch("");
                    setGroupFilter("");
                    setCategoryFilter("");
                    setAssigneeFilter("");
                    setPriorityFilter("");
                  }}
                >
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

        {/* Pagination Bar */}
        {!loading && totalCount > 0 && (
          <div className="flex items-center justify-between px-1 text-meta tabular-nums">
            <span>
              Showing {rangeStart}–{rangeEnd} of {totalCount} ticket(s)
            </span>
            <div className="flex items-center gap-1.5">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={page === 0}
                onClick={() => setPage((p) => Math.max(0, p - 1))}
              >
                <ChevronLeft className="size-3.5" strokeWidth={1.5} />
                <span>Prev</span>
              </Button>
              <span className="px-2">
                Page {page + 1} / {totalPages}
              </span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={page + 1 >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                <span>Next</span>
                <ChevronRight className="size-3.5" strokeWidth={1.5} />
              </Button>
            </div>
          </div>
        )}
      </div>

      <WalkupTicketModal
        open={walkupOpen}
        onClose={() => setWalkupOpen(false)}
        meta={meta}
        onCreated={(created) => {
          const target = `/workspace/tickets/${created.id}`;
          startNavigation(target);
          router.push(target);
        }}
      />
    </AppShell>
  );
}
