"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  BookOpen,
  Check,
  Copy,
  Lock,
  Monitor,
  Paperclip,
  PanelRight,
  Send,
  X,
} from "lucide-react";

import { AppShell } from "@/components/AppShell";
import { useNavigationProgress } from "@/components/NavigationProgress";
import {
  PasteImageUploader,
  PasteUploaderHandle,
} from "@/components/PasteImageUploader";
import { QueueRow } from "@/components/QueueRow";
import { SaveTicketToKbModal } from "@/components/SaveTicketToKbModal";
import { TicketTimeline } from "@/components/TicketTimeline";
import {
  Avatar,
  Button,
  PriorityGlyph,
  SkeletonRow,
  SlaBadge,
  StatusBadge,
  TopicBadge,
  selectBaseClass,
} from "@/components/ui/primitives";
import { api, buildAttachmentUrl } from "@/lib/api";
import { cn } from "@/lib/cn";
import {
  extractUltraViewFromText,
  formatDurationCompact,
  formatRelativeTime,
  formatUltraViewId,
  PRIORITY_LABELS,
} from "@/lib/formatters";
import {
  Attachment,
  KbArticleDetail,
  Ticket,
  TicketDetail,
  TicketMetadata,
  TicketPriority,
  TicketStatus,
} from "@/lib/types";
import { useRealtime } from "@/lib/use-realtime";

const PRIORITY_ORDER: TicketPriority[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];

export default function WorkspaceTicketDetailPage() {
  const params = useParams<{ id: string }>();
  const ticketId = params.id;
  const router = useRouter();
  const { startNavigation } = useNavigationProgress();

  const [queueTickets, setQueueTickets] = useState<Ticket[]>([]);
  const [ticket, setTicket] = useState<TicketDetail | null>(null);
  const [meta, setMeta] = useState<TicketMetadata | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Composer state: isolated drafts per tab (§9.4)
  const [composerTab, setComposerTab] = useState<"reply" | "note">("reply");
  const [replyDraft, setReplyDraft] = useState("");
  const [noteDraft, setNoteDraft] = useState("");
  const [replyAttachments, setReplyAttachments] = useState<Attachment[]>([]);
  const [noteAttachments, setNoteAttachments] = useState<Attachment[]>([]);
  const [showUploader, setShowUploader] = useState(false);
  const [sending, setSending] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);

  // Mobile properties sheet (§13) & Knowledge Base helpers
  const [mobilePropsOpen, setMobilePropsOpen] = useState(false);
  const [saveKbOpen, setSaveKbOpen] = useState(false);
  const [kbInsertOpen, setKbInsertOpen] = useState(false);
  const [kbInsertQuery, setKbInsertQuery] = useState("");
  const [kbArticles, setKbArticles] = useState<KbArticleDetail[]>([]);
  const [kbLoaded, setKbLoaded] = useState(false);
  const [copiedId, setCopiedId] = useState(false);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  const uploaderRef = useRef<PasteUploaderHandle | null>(null);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);

  const loadData = useCallback(async () => {
    setError(null);
    try {
      const [detail, metadata, list] = await Promise.all([
        api.getTicket(ticketId),
        api.getMetadata(),
        api.listTickets({ limit: 80 }),
      ]);
      setTicket(detail);
      setMeta(metadata);
      setQueueTickets(list.items);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load ticket");
    } finally {
      setLoading(false);
    }
  }, [ticketId]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  useRealtime(() => {
    void loadData();
  });

  const handleCopyText = async (key: string, value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopiedKey(key);
      window.setTimeout(() => setCopiedKey(null), 1500);
    } catch {
      // ignore clipboard restrictions
    }
  };

  const handleRequestUltraView = async () => {
    setActionBusy(true);
    try {
      await api.requestUltraView(ticketId);
      await loadData();
    } finally {
      setActionBusy(false);
    }
  };

  // Keyboard shortcuts: Cmd/Ctrl + Shift + R / N (§9.1) and R to focus reply (§13)
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.shiftKey) {
        if (e.key.toLowerCase() === "r") {
          e.preventDefault();
          setComposerTab("reply");
          composerRef.current?.focus();
        } else if (e.key.toLowerCase() === "n") {
          e.preventDefault();
          setComposerTab("note");
          composerRef.current?.focus();
        }
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const groupedQueue = useMemo(() => {
    const map: Record<TicketPriority, Ticket[]> = {
      CRITICAL: [],
      HIGH: [],
      MEDIUM: [],
      LOW: [],
    };
    for (const t of queueTickets) {
      map[t.priority].push(t);
    }
    return map;
  }, [queueTickets]);

  const handleClaim = async () => {
    setActionBusy(true);
    try {
      await api.claimTicket(ticketId);
      await loadData();
    } finally {
      setActionBusy(false);
    }
  };

  const handleStatusChange = async (nextStatus: TicketStatus) => {
    setActionBusy(true);
    try {
      await api.updateTicketStatus(ticketId, nextStatus);
      await loadData();
    } finally {
      setActionBusy(false);
    }
  };

  const handleAssignUpdate = async (
    patch: { support_group_id?: string | null; assignee_id?: string | null }
  ) => {
    if (!ticket) return;
    setActionBusy(true);
    try {
      await api.assignTicket(ticketId, {
        support_group_id:
          patch.support_group_id !== undefined
            ? patch.support_group_id
            : ticket.support_group_id,
        assignee_id:
          patch.assignee_id !== undefined ? patch.assignee_id : ticket.assignee_id,
      });
      await loadData();
    } finally {
      setActionBusy(false);
    }
  };

  const handlePriorityChange = async (nextPriority: TicketPriority) => {
    if (!ticket || ticket.priority === nextPriority) return;
    setActionBusy(true);
    try {
      await api.updateTicketPriority(ticketId, nextPriority);
      await loadData();
    } finally {
      setActionBusy(false);
    }
  };

  const currentDraft = composerTab === "reply" ? replyDraft : noteDraft;
  const setCurrentDraft = composerTab === "reply" ? setReplyDraft : setNoteDraft;

  const handleToggleKbInsert = async () => {
    const next = !kbInsertOpen;
    setKbInsertOpen(next);
    if (next && !kbLoaded) {
      try {
        const res = await api.listKbArticles();
        setKbArticles(res.items);
        setKbLoaded(true);
      } catch {
        // ignore transient error
      }
    }
  };

  const handleInsertKbArticle = (art: KbArticleDetail) => {
    const lines: string[] = [art.title];
    if (art.steps.length > 0) {
      lines.push(...art.steps.map((s, idx) => `${idx + 1}. ${s}`));
    }
    if (composerTab === "note" && art.notes) {
      lines.push("", art.notes);
    }
    const snippet = lines.join("\n");
    setCurrentDraft((prev) => (prev.trim() ? `${prev.trimEnd()}\n\n${snippet}` : snippet));
    setKbInsertOpen(false);
    setKbInsertQuery("");
    window.setTimeout(() => composerRef.current?.focus(), 30);
  };
  const currentAttachments =
    composerTab === "reply" ? replyAttachments : noteAttachments;
  const setCurrentAttachments =
    composerTab === "reply" ? setReplyAttachments : setNoteAttachments;

  const handleComposerPaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const items = Array.from(e.clipboardData?.items || []);
    const files = items
      .filter((it) => it.kind === "file")
      .map((it) => it.getAsFile())
      .filter((f): f is File => Boolean(f));
    if (files.length > 0) {
      e.preventDefault();
      setShowUploader(true);
      void uploaderRef.current?.uploadFiles(files);
    }
  };

  const handleSendComposer = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const text = currentDraft.trim();
    if (!text || sending) return;
    setSending(true);
    const isInternal = composerTab === "note";
    try {
      await api.addComment(ticketId, {
        body: text,
        is_internal: isInternal,
        attachment_ids: currentAttachments.map((a) => a.id),
      });
      if (isInternal) {
        setNoteDraft("");
        setNoteAttachments([]);
        // Stay on Internal note tab (§9.4)
      } else {
        setReplyDraft("");
        setReplyAttachments([]);
      }
      setShowUploader(false);
      await loadData();
    } finally {
      setSending(false);
    }
  };

  const copyTicketCode = async () => {
    if (!ticket) return;
    try {
      await navigator.clipboard.writeText(ticket.ticket_code);
      setCopiedId(true);
      window.setTimeout(() => setCopiedId(false), 1500);
    } catch {
      // ignore clipboard restrictions
    }
  };

  const propertiesContent = ticket && (
    <div className="space-y-4">
      <div className="space-y-1">
        <div className="grid grid-cols-[96px_minmax(0,1fr)] items-center gap-x-3 min-h-[32px]">
          <span className="text-meta">Status</span>
          <div>
            <StatusBadge status={ticket.status} />
          </div>
        </div>

        {ticket.status !== "CANCELLED" && (
          <div className="grid grid-cols-[96px_minmax(0,1fr)] items-center gap-x-3 min-h-[32px]">
            <span className="text-meta">SLA</span>
            <div>
              <SlaBadge ticket={ticket} />
            </div>
          </div>
        )}

        <div className="grid grid-cols-[96px_minmax(0,1fr)] items-center gap-x-3 min-h-[32px]">
          <span className="text-meta">Priority</span>
          <div className="flex items-center gap-1 min-w-0">
            <PriorityGlyph priority={ticket.priority} />
            <select
              disabled={
                actionBusy ||
                ticket.status === "CLOSED" ||
                ticket.status === "CANCELLED"
              }
              value={ticket.priority}
              onChange={(e) =>
                void handlePriorityChange(e.target.value as TicketPriority)
              }
              aria-label="Ticket priority"
              className={cn(
                selectBaseClass,
                "h-7 border-transparent bg-transparent hover:border-border hover:bg-card px-1.5"
              )}
            >
              {PRIORITY_ORDER.map((p) => (
                <option key={p} value={p}>
                  {PRIORITY_LABELS[p]}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="grid grid-cols-[96px_minmax(0,1fr)] items-center gap-x-3 min-h-[32px]">
          <span className="text-meta">Category</span>
          <div>
            {ticket.category ? (
              <TopicBadge
                label={ticket.category.name}
                iconSlug={ticket.category.slug}
              />
            ) : (
              <span className="text-body text-faint">—</span>
            )}
          </div>
        </div>

        <div className="grid grid-cols-[96px_minmax(0,1fr)] items-center gap-x-3 min-h-[32px]">
          <span className="text-meta">Asset Code</span>
          <div>
            {ticket.asset_code ? (
              <TopicBadge label={ticket.asset_code} iconSlug="asset" mono />
            ) : (
              <span className="text-body text-faint">—</span>
            )}
          </div>
        </div>

        <div className="grid grid-cols-[96px_minmax(0,1fr)] items-center gap-x-3 min-h-[32px]">
          <span className="text-meta">Group</span>
          <select
            disabled={actionBusy}
            value={ticket.support_group_id || ""}
            onChange={(e) =>
              void handleAssignUpdate({ support_group_id: e.target.value || null })
            }
            className={cn(
              selectBaseClass,
              "h-7 border-transparent bg-transparent hover:border-border hover:bg-card px-1.5 -ml-1.5"
            )}
          >
            <option value="">—</option>
            {meta?.support_groups.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
          </select>
        </div>

        <div className="grid grid-cols-[96px_minmax(0,1fr)] items-center gap-x-3 min-h-[32px]">
          <span className="text-meta">Assignee</span>
          <select
            disabled={actionBusy}
            value={ticket.assignee_id || ""}
            onChange={(e) =>
              void handleAssignUpdate({ assignee_id: e.target.value || null })
            }
            className={cn(
              selectBaseClass,
              "h-7 border-transparent bg-transparent hover:border-border hover:bg-card px-1.5 -ml-1.5"
            )}
          >
            <option value="">Unassigned</option>
            {meta?.it_agents.map((ag) => (
              <option key={ag.id} value={ag.id}>
                {ag.full_name}
              </option>
            ))}
          </select>
        </div>

        {ticket.total_paused_seconds > 0 && (
          <div className="grid grid-cols-[96px_minmax(0,1fr)] items-center gap-x-3 min-h-[32px]">
            <span className="text-meta">Paused SLA</span>
            <span className="text-body tabular-nums">
              {formatDurationCompact(ticket.total_paused_seconds)}
            </span>
          </div>
        )}
      </div>

      {/* Remote Support (UltraViewer) */}
      <div className="border-t border-border pt-3 space-y-1.5">
        <div className="flex items-center justify-between gap-2">
          <span className="inline-flex items-center gap-1.5 text-meta">
            <Monitor className="size-3.5 text-faint" strokeWidth={1.5} />
            <span>UltraViewer</span>
          </span>
          <span className="text-meta-faint">
            {ticket.custom_data?.ultraview?.state === "READY"
              ? "Ready"
              : ticket.custom_data?.ultraview?.state === "REQUESTED"
              ? "Requested"
              : "—"}
          </span>
        </div>

        {ticket.custom_data?.ultraview?.id ? (
          <div className="space-y-1.5">
            <div className="grid grid-cols-[52px_minmax(0,1fr)_auto] items-center gap-2 min-h-[28px]">
              <span className="text-meta">ID</span>
              <span className="text-body font-mono tabular-nums truncate">
                {formatUltraViewId(ticket.custom_data.ultraview.id)}
              </span>
              <button
                type="button"
                onClick={() =>
                  void handleCopyText("panel-id", String(ticket.custom_data.ultraview.id))
                }
                className="inline-flex h-6 items-center gap-1 rounded-sm border border-border bg-card px-2 text-[13px] text-foreground hover:bg-muted"
              >
                {copiedKey === "panel-id" ? (
                  <Check className="size-3" strokeWidth={1.5} />
                ) : (
                  <Copy className="size-3 text-muted-foreground" strokeWidth={1.5} />
                )}
                <span>{copiedKey === "panel-id" ? "Copied" : "Copy"}</span>
              </button>
            </div>

            {ticket.custom_data.ultraview.pass && (
              <div className="grid grid-cols-[52px_minmax(0,1fr)_auto] items-center gap-2 min-h-[28px]">
                <span className="text-meta">Pass</span>
                <span className="text-body font-mono tabular-nums truncate">
                  {ticket.custom_data.ultraview.pass}
                </span>
                <button
                  type="button"
                  onClick={() =>
                    void handleCopyText(
                      "panel-pass",
                      String(ticket.custom_data.ultraview.pass)
                    )
                  }
                  className="inline-flex h-6 items-center gap-1 rounded-sm border border-border bg-card px-2 text-[13px] text-foreground hover:bg-muted"
                >
                  {copiedKey === "panel-pass" ? (
                    <Check className="size-3" strokeWidth={1.5} />
                  ) : (
                    <Copy className="size-3 text-muted-foreground" strokeWidth={1.5} />
                  )}
                  <span>{copiedKey === "panel-pass" ? "Copied" : "Copy"}</span>
                </button>
              </div>
            )}
          </div>
        ) : (
          <p className="text-meta-faint">
            Click Request UltraViewer to prompt the user for ID &amp; Pass.
          </p>
        )}
      </div>

      {/* Requester Block (§6) */}
      <div className="border-t border-border pt-4 space-y-1.5">
        <div className="flex items-center gap-2 pb-1">
          <Avatar name={ticket.requester.full_name} />
          <span className="text-body-strong truncate">{ticket.requester.full_name}</span>
        </div>

        <div className="grid grid-cols-[96px_minmax(0,1fr)] items-center gap-x-3 min-h-[28px]">
          <span className="text-meta">Email</span>
          <span className="text-body truncate">{ticket.requester.email}</span>
        </div>

        <div className="grid grid-cols-[96px_minmax(0,1fr)] items-center gap-x-3 min-h-[28px]">
          <span className="text-meta">ID</span>
          <div className="group flex items-center justify-between gap-1 min-w-0">
            <span className="text-body font-mono tabular-nums truncate">
              {ticket.ticket_code}
            </span>
            <button
              type="button"
              onClick={() => void copyTicketCode()}
              className="p-1 rounded-xs text-faint hover:text-foreground opacity-0 group-hover:opacity-100 transition-opacity duration-75"
              title="Copy ticket ID"
            >
              {copiedId ? (
                <Check className="size-3.5" strokeWidth={1.5} />
              ) : (
                <Copy className="size-3.5" strokeWidth={1.5} />
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Timeline */}
      <div className="border-t border-border pt-4 space-y-3">
        <p className="text-meta">Timeline</p>
        <TicketTimeline events={ticket.timeline} />
      </div>
    </div>
  );

  return (
    <AppShell fullBleed>
      <div className="h-[calc(100dvh-44px)] grid grid-cols-1 md:grid-cols-[340px_minmax(0,1fr)] xl:grid-cols-[340px_minmax(0,1fr)_300px] overflow-hidden">
        {/* Column 1: Queue List (340px) */}
        <aside className="hidden md:block border-r border-border bg-background overflow-y-auto">
          <div className="h-11 px-4 border-b border-border flex items-center justify-between bg-background sticky top-0 z-10">
            <span className="text-body-strong">Queue</span>
            <span className="text-meta tabular-nums">{queueTickets.length}</span>
          </div>

          {PRIORITY_ORDER.map((priority) => {
            const rows = groupedQueue[priority];
            if (!rows.length) return null;
            return (
              <div key={priority}>
                <div className="h-9 px-4 flex items-center gap-2 border-b border-border-subtle bg-background">
                  <PriorityGlyph priority={priority} />
                  <span className="text-[13px] font-medium text-foreground">
                    {PRIORITY_LABELS[priority]}
                  </span>
                  <span className="text-[13px] text-muted-foreground tabular-nums">
                    {rows.length}
                  </span>
                </div>
                {rows.map((item) => (
                  <QueueRow
                    key={item.id}
                    ticket={item}
                    selected={item.id === ticketId}
                    layout="compact"
                    onClick={() => {
                      const target = `/workspace/tickets/${item.id}`;
                      startNavigation(target);
                      router.push(target);
                    }}
                  />
                ))}
              </div>
            );
          })}
        </aside>

        {/* Column 2: Conversation & Composer (flex-1, max-w-[760px] content) */}
        <section className="flex flex-col min-w-0 bg-card overflow-hidden">
          {/* Header 44px */}
          <div className="h-11 px-4 border-b border-border flex items-center justify-between gap-3 shrink-0">
            <div className="flex items-center gap-2.5 min-w-0">
              <Link
                href="/workspace"
                className="md:hidden text-muted-foreground hover:text-foreground"
                aria-label="Back to queue"
              >
                <ArrowLeft className="size-4" strokeWidth={1.5} />
              </Link>
              {ticket && (
                <>
                  <span className="text-meta font-mono tabular-nums shrink-0">
                    {ticket.ticket_code}
                  </span>
                  <h1 className="text-body-strong truncate">{ticket.title}</h1>
                </>
              )}
            </div>

            {ticket && (
              <div className="flex items-center gap-2 shrink-0">
                <Button
                  variant="outline"
                  onClick={() => setSaveKbOpen(true)}
                  title="Save solution or troubleshooting tip to Knowledge Base"
                >
                  <BookOpen className="size-3.5" strokeWidth={1.5} />
                  <span className="hidden lg:inline">Save as KB</span>
                </Button>

                {ticket.status !== "CLOSED" &&
                  ticket.status !== "CANCELLED" &&
                  ticket.status !== "RESOLVED" && (
                    <Button
                      variant="outline"
                      disabled={actionBusy}
                      onClick={() => void handleRequestUltraView()}
                    >
                      <Monitor className="size-3.5" strokeWidth={1.5} />
                      <span>Request UltraViewer</span>
                    </Button>
                  )}

                {!ticket.assignee_id &&
                  ticket.status !== "CLOSED" &&
                  ticket.status !== "CANCELLED" && (
                    <Button
                      variant="outline"
                      disabled={actionBusy}
                      onClick={() => void handleClaim()}
                    >
                      Assign to me
                    </Button>
                  )}

                {ticket.status === "IN_PROGRESS" && (
                  <Button
                    variant="outline"
                    disabled={actionBusy}
                    onClick={() => void handleStatusChange("WAITING_FOR_USER")}
                  >
                    Wait on user
                  </Button>
                )}

                {ticket.status === "WAITING_FOR_USER" && (
                  <Button
                    variant="outline"
                    disabled={actionBusy}
                    onClick={() => void handleStatusChange("IN_PROGRESS")}
                  >
                    Resume work
                  </Button>
                )}

                {(ticket.status === "IN_PROGRESS" ||
                  ticket.status === "WAITING_FOR_USER" ||
                  ticket.status === "REOPENED") && (
                  <Button
                    variant="primary"
                    disabled={actionBusy}
                    onClick={() => void handleStatusChange("RESOLVED")}
                  >
                    Resolve
                  </Button>
                )}

                <Button
                  variant="icon"
                  className="xl:hidden"
                  onClick={() => setMobilePropsOpen(true)}
                  aria-label="Open properties"
                >
                  <PanelRight className="size-4" strokeWidth={1.5} />
                </Button>
              </div>
            )}
          </div>

          {/* Scrollable Thread */}
          <div className="flex-1 overflow-y-auto px-4 py-4">
            {error ? (
              <div className="max-w-[760px] rounded-md border border-destructive/30 bg-destructive/5 px-4 py-3 text-[13px] text-destructive">
                {error}
              </div>
            ) : loading || !ticket ? (
              <div className="max-w-[760px] rounded-lg border border-border bg-card overflow-hidden">
                <SkeletonRow count={3} compact />
              </div>
            ) : (
              <div className="max-w-[760px] space-y-5">
                {/* Initial Ticket Message (no bubble) */}
                <div>
                  <div className="flex items-center gap-2">
                    <Avatar name={ticket.requester.full_name} />
                    <span className="text-body-strong">{ticket.requester.full_name}</span>
                    <span className="text-meta-faint tabular-nums">
                      {formatRelativeTime(ticket.created_at)}
                    </span>
                  </div>
                  <p className="pl-8 mt-1 text-body whitespace-pre-wrap">
                    {ticket.description}
                  </p>
                  {ticket.attachments.length > 0 && (
                    <div className="pl-8 mt-2 flex flex-wrap gap-2">
                      {ticket.attachments.map((att) => (
                        <a
                          key={att.id}
                          href={buildAttachmentUrl(att.download_url)}
                          target="_blank"
                          rel="noreferrer"
                          className="rounded-sm border border-border overflow-hidden hover:border-foreground/40"
                        >
                          {att.content_type.startsWith("image/") ? (
                            <img
                              src={buildAttachmentUrl(att.download_url)}
                              alt={att.file_name}
                              className="h-24 w-auto object-cover"
                            />
                          ) : (
                            <span className="px-2.5 py-1.5 text-[13px] text-foreground inline-block">
                              {att.file_name}
                            </span>
                          )}
                        </a>
                      ))}
                    </div>
                  )}
                </div>

                {/* Replies & Internal Notes (§9.3) */}
                {ticket.comments.map((c) => {
                  if (c.is_internal) {
                    return (
                      <div
                        key={c.id}
                        className="anim-fade-up rounded-md border border-note-border bg-note px-3 py-2"
                      >
                        <div className="flex items-center gap-2">
                          <Avatar name={c.author.full_name} />
                          <span className="text-body-strong">{c.author.full_name}</span>
                          <span className="text-meta-faint tabular-nums">
                            {formatRelativeTime(c.created_at)}
                          </span>
                          <span className="inline-flex items-center gap-1 text-meta text-note-ink ml-1">
                            <Lock className="size-3" strokeWidth={1.5} />
                            <span>Internal note</span>
                          </span>
                        </div>
                        <p className="pl-8 mt-1 text-body whitespace-pre-wrap">{c.body}</p>
                      {(() => {
                        const uv = extractUltraViewFromText(c.body);
                        if (!uv) return null;
                        return (
                          <div className="pl-8 mt-1.5 flex flex-wrap items-center gap-2">
                            <button
                              type="button"
                              onClick={() => void handleCopyText(`msg-id-${c.id}`, uv.id)}
                              className="inline-flex h-6 items-center gap-1.5 rounded-sm border border-border bg-card px-2 text-[13px] text-foreground hover:bg-muted tabular-nums"
                            >
                              {copiedKey === `msg-id-${c.id}` ? (
                                <Check className="size-3" strokeWidth={1.5} />
                              ) : (
                                <Copy className="size-3 text-muted-foreground" strokeWidth={1.5} />
                              )}
                              <span>
                                {copiedKey === `msg-id-${c.id}`
                                  ? "Copied ID"
                                  : `Copy ID: ${formatUltraViewId(uv.id)}`}
                              </span>
                            </button>
                            <button
                              type="button"
                              onClick={() => void handleCopyText(`msg-pass-${c.id}`, uv.pass)}
                              className="inline-flex h-6 items-center gap-1.5 rounded-sm border border-border bg-card px-2 text-[13px] text-foreground hover:bg-muted tabular-nums"
                            >
                              {copiedKey === `msg-pass-${c.id}` ? (
                                <Check className="size-3" strokeWidth={1.5} />
                              ) : (
                                <Copy className="size-3 text-muted-foreground" strokeWidth={1.5} />
                              )}
                              <span>
                                {copiedKey === `msg-pass-${c.id}`
                                  ? "Copied Pass"
                                  : `Copy Pass: ${uv.pass}`}
                              </span>
                            </button>
                          </div>
                        );
                      })()}
                        {c.attachments.length > 0 && (
                          <div className="pl-8 mt-2 flex flex-wrap gap-2">
                            {c.attachments.map((att) => (
                              <a
                                key={att.id}
                                href={buildAttachmentUrl(att.download_url)}
                                target="_blank"
                                rel="noreferrer"
                              >
                                <img
                                  src={buildAttachmentUrl(att.download_url)}
                                  alt={att.file_name}
                                  className="h-24 rounded-sm border border-note-border"
                                />
                              </a>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  }

                  return (
                    <div key={c.id} className="anim-fade-up">
                      <div className="flex items-center gap-2">
                        <Avatar name={c.author.full_name} />
                        <span className="text-body-strong">{c.author.full_name}</span>
                        <span className="text-meta-faint tabular-nums">
                          {formatRelativeTime(c.created_at)}
                        </span>
                      </div>
                      <p className="pl-8 mt-1 text-body whitespace-pre-wrap">{c.body}</p>
                      {(() => {
                        const uv = extractUltraViewFromText(c.body);
                        if (!uv) return null;
                        return (
                          <div className="pl-8 mt-1.5 flex flex-wrap items-center gap-2">
                            <button
                              type="button"
                              onClick={() => void handleCopyText(`msg-id-${c.id}`, uv.id)}
                              className="inline-flex h-6 items-center gap-1.5 rounded-sm border border-border bg-card px-2 text-[13px] text-foreground hover:bg-muted tabular-nums"
                            >
                              {copiedKey === `msg-id-${c.id}` ? (
                                <Check className="size-3" strokeWidth={1.5} />
                              ) : (
                                <Copy className="size-3 text-muted-foreground" strokeWidth={1.5} />
                              )}
                              <span>
                                {copiedKey === `msg-id-${c.id}`
                                  ? "Copied ID"
                                  : `Copy ID: ${formatUltraViewId(uv.id)}`}
                              </span>
                            </button>
                            <button
                              type="button"
                              onClick={() => void handleCopyText(`msg-pass-${c.id}`, uv.pass)}
                              className="inline-flex h-6 items-center gap-1.5 rounded-sm border border-border bg-card px-2 text-[13px] text-foreground hover:bg-muted tabular-nums"
                            >
                              {copiedKey === `msg-pass-${c.id}` ? (
                                <Check className="size-3" strokeWidth={1.5} />
                              ) : (
                                <Copy className="size-3 text-muted-foreground" strokeWidth={1.5} />
                              )}
                              <span>
                                {copiedKey === `msg-pass-${c.id}`
                                  ? "Copied Pass"
                                  : `Copy Pass: ${uv.pass}`}
                              </span>
                            </button>
                          </div>
                        );
                      })()}
                      {c.attachments.length > 0 && (
                        <div className="pl-8 mt-2 flex flex-wrap gap-2">
                          {c.attachments.map((att) => (
                            <a
                              key={att.id}
                              href={buildAttachmentUrl(att.download_url)}
                              target="_blank"
                              rel="noreferrer"
                            >
                              <img
                                src={buildAttachmentUrl(att.download_url)}
                                alt={att.file_name}
                                className="h-24 rounded-sm border border-border"
                              />
                            </a>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Pinned Bottom Composer (§9.1–§9.4) */}
          {ticket && (
            <div className="px-4 pb-4 pt-2 border-t border-border-subtle bg-card shrink-0">
              <form
                onSubmit={handleSendComposer}
                className={cn(
                  "max-w-[760px] rounded-md border p-4 transition-colors duration-150 ease-out",
                  composerTab === "note"
                    ? "bg-note border-note-border"
                    : "bg-card border-border"
                )}
              >
                {/* Underline Tabs (§9.1) */}
                <div className="flex items-center border-b border-border-subtle mb-2.5">
                  <button
                    type="button"
                    title="Reply (⌘⇧R)"
                    onClick={() => setComposerTab("reply")}
                    className={cn(
                      "h-8 px-0 mr-4 text-[13px] font-medium border-b-2 -mb-px transition-colors duration-75",
                      composerTab === "reply"
                        ? "text-foreground border-foreground"
                        : "text-muted-foreground border-transparent hover:text-foreground"
                    )}
                  >
                    Reply
                  </button>
                  <button
                    type="button"
                    title="Internal note (⌘⇧N)"
                    onClick={() => setComposerTab("note")}
                    className={cn(
                      "h-8 px-0 mr-4 text-[13px] font-medium border-b-2 -mb-px inline-flex items-center gap-1.5 transition-colors duration-75",
                      composerTab === "note"
                        ? "text-foreground border-foreground"
                        : "text-muted-foreground border-transparent hover:text-foreground"
                    )}
                  >
                    <Lock className="size-3.5 text-note-ink" strokeWidth={1.5} />
                    <span>Internal note</span>
                  </button>
                </div>

                {/* Recipient / Team-only indicator (§9.2) */}
                <div className="flex items-center justify-between gap-2 mb-2">
                  {composerTab === "reply" ? (
                    <span className="text-meta truncate">
                      To: {ticket.requester.email}
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 text-meta text-note-ink">
                      <Lock className="size-3.5" strokeWidth={1.5} />
                      <span>Visible to your team only</span>
                    </span>
                  )}

                  {composerTab === "reply" && replyDraft.trimStart().startsWith("@") && (
                    <span className="text-meta text-destructive">
                      Khách hàng sẽ thấy tin này
                    </span>
                  )}
                </div>

                <textarea
                  ref={composerRef}
                  rows={3}
                  value={currentDraft}
                  onChange={(e) => setCurrentDraft(e.target.value)}
                  onPaste={handleComposerPaste}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                      e.preventDefault();
                      void handleSendComposer();
                    }
                  }}
                  placeholder={
                    composerTab === "reply"
                      ? `Write a reply to ${ticket.requester.full_name}… (Ctrl+V to paste screenshot)`
                      : "Add an internal note. Only your team can see this."
                  }
                  className="w-full resize-none bg-transparent text-body placeholder:text-faint focus:outline-none"
                />

                {(showUploader || currentAttachments.length > 0) && (
                  <div className="mt-2">
                    <PasteImageUploader
                      ref={uploaderRef}
                      ticketId={ticket.id}
                      attachments={currentAttachments}
                      onChange={setCurrentAttachments}
                      compact
                    />
                  </div>
                )}

                <div className="flex items-center justify-between pt-3 mt-1 relative">
                  <div className="flex items-center gap-3 text-faint">
                    <button
                      type="button"
                      onClick={() => setShowUploader((v) => !v)}
                      className="hover:text-foreground transition-colors duration-75"
                      title="Attach or paste file (Ctrl+V)"
                    >
                      <Paperclip className="size-4" strokeWidth={1.5} />
                    </button>

                    <button
                      type="button"
                      onClick={() => void handleToggleKbInsert()}
                      className="inline-flex items-center gap-1 text-[13px] hover:text-foreground transition-colors duration-75"
                      title="Insert solution steps from Knowledge Base"
                    >
                      <BookOpen className="size-3.5" strokeWidth={1.5} />
                      <span>Insert KB</span>
                    </button>
                  </div>

                  {kbInsertOpen && (
                    <div className="anim-popover absolute left-0 bottom-11 z-30 w-80 max-w-[calc(100vw-2rem)] rounded-lg border border-border bg-popover shadow-popover overflow-hidden">
                      <div className="p-2 border-b border-border flex items-center gap-2">
                        <input
                          type="text"
                          autoFocus
                          value={kbInsertQuery}
                          onChange={(e) => setKbInsertQuery(e.target.value)}
                          placeholder="Search KB tip to insert..."
                          className="w-full h-7 px-2.5 rounded-sm border border-input bg-card text-[13px] text-foreground placeholder:text-faint focus:outline-none focus:ring-2 focus:ring-ring/20"
                        />
                        <button
                          type="button"
                          onClick={() => setKbInsertOpen(false)}
                          className="text-faint hover:text-foreground shrink-0"
                          aria-label="Close KB picker"
                        >
                          <X className="size-3.5" strokeWidth={1.5} />
                        </button>
                      </div>
                      <div className="max-h-56 overflow-y-auto divide-y divide-border-subtle">
                        {kbArticles
                          .filter((a) => {
                            const q = kbInsertQuery.trim().toLowerCase();
                            if (!q) return true;
                            return (
                              a.title.toLowerCase().includes(q) ||
                              a.keywords.some((k) => k.toLowerCase().includes(q))
                            );
                          })
                          .slice(0, 8)
                          .map((art) => (
                            <button
                              key={art.id}
                              type="button"
                              onClick={() => handleInsertKbArticle(art)}
                              className="w-full text-left px-3 py-2 hover:bg-muted/60 transition-colors duration-75"
                            >
                              <p className="text-[13px] font-medium text-foreground truncate">
                                {art.title}
                              </p>
                              <p className="text-[12px] text-muted-foreground truncate">
                                {art.visibility === "INTERNAL" ? "IT Runbook" : "Self-Help"}
                                {art.category ? ` · ${art.category.name}` : ""}
                                {` · ${art.steps.length} steps`}
                              </p>
                            </button>
                          ))}
                      </div>
                    </div>
                  )}

                  <Button
                    type="submit"
                    variant={composerTab === "note" ? "note" : "primary"}
                    disabled={!currentDraft.trim() || sending}
                  >
                    {composerTab === "note" ? (
                      <Lock className="size-3.5" strokeWidth={1.5} />
                    ) : (
                      <Send className="size-3.5" strokeWidth={1.5} />
                    )}
                    <span>
                      {composerTab === "note" ? "Add note" : "Send reply"}
                    </span>
                  </Button>
                </div>
              </form>
            </div>
          )}
        </section>

        {/* Column 3: Properties Panel (300px) */}
        <aside className="hidden xl:block border-l border-border bg-background overflow-y-auto p-4">
          {propertiesContent}
        </aside>
      </div>

      {/* Mobile/Tablet Properties Sheet (§13) */}
      {mobilePropsOpen && (
        <div
          role="dialog"
          aria-modal="true"
          onClick={() => setMobilePropsOpen(false)}
          className="anim-scrim fixed inset-0 z-50 bg-[var(--scrim)] backdrop-blur-[2px] flex justify-end xl:hidden"
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="anim-sheet-right w-[300px] h-full bg-background border-l border-border p-4 overflow-y-auto shadow-popover"
          >
            <div className="flex items-center justify-between pb-3 mb-3 border-b border-border">
              <span className="text-body-strong">Properties</span>
              <Button variant="icon" onClick={() => setMobilePropsOpen(false)}>
                <X className="size-4" strokeWidth={1.5} />
              </Button>
            </div>
            {propertiesContent}
          </div>
        </div>
      )}

      {ticket && (
        <SaveTicketToKbModal
          open={saveKbOpen}
          onClose={() => setSaveKbOpen(false)}
          ticket={ticket}
          categories={meta?.categories || []}
        />
      )}
    </AppShell>
  );
}
