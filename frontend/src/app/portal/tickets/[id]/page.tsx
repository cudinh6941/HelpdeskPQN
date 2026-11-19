"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Monitor, Paperclip, RotateCcw, Send, Star, XCircle } from "lucide-react";

import { AppShell } from "@/components/AppShell";
import {
  PasteImageUploader,
  PasteUploaderHandle,
} from "@/components/PasteImageUploader";
import { TicketTimeline } from "@/components/TicketTimeline";
import {
  Avatar,
  Button,
  PriorityGlyph,
  SkeletonRow,
  SlaBadge,
  StatusBadge,
  TopicBadge,
  inputBaseClass,
} from "@/components/ui/primitives";
import { api, buildAttachmentUrl } from "@/lib/api";
import {
  formatDateTime,
  formatRelativeTime,
  formatUltraViewId,
  PRIORITY_LABELS,
} from "@/lib/formatters";
import { Attachment, TicketDetail } from "@/lib/types";
import { useRealtime } from "@/lib/use-realtime";

export default function PortalTicketDetailPage() {
  const params = useParams<{ id: string }>();
  const ticketId = params.id;

  const [ticket, setTicket] = useState<TicketDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [commentBody, setCommentBody] = useState("");
  const [commentAttachments, setCommentAttachments] = useState<Attachment[]>([]);
  const [showUploader, setShowUploader] = useState(false);
  const [sending, setSending] = useState(false);

  const [rating, setRating] = useState(5);
  const [feedback, setFeedback] = useState("");
  const [ratingBusy, setRatingBusy] = useState(false);

  const [showUvForm, setShowUvForm] = useState(false);
  const [uvId, setUvId] = useState("");
  const [uvPass, setUvPass] = useState("");
  const [uvBusy, setUvBusy] = useState(false);

  const uploaderRef = useRef<PasteUploaderHandle | null>(null);
  const uvPassInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const savedUvId = window.localStorage.getItem("helpdesk_uv_id");
      if (savedUvId) setUvId(savedUvId);
    }
  }, []);

  const loadTicket = useCallback(async () => {
    try {
      const data = await api.getTicket(ticketId);
      setTicket(data);
      const uvData = data.custom_data?.ultraview;
      if (uvData?.id) {
        setUvId(uvData.id);
      }
      if (uvData?.state === "REQUESTED") {
        setShowUvForm(true);
        window.setTimeout(() => uvPassInputRef.current?.focus(), 50);
      }
    } finally {
      setLoading(false);
    }
  }, [ticketId]);

  useEffect(() => {
    void loadTicket();
  }, [loadTicket]);

  useRealtime((evt) => {
    if (evt.ticket_id === ticketId) {
      void loadTicket();
    }
  });

  const handleProvideUv = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uvId.trim() || !uvPass.trim() || uvBusy) return;
    setUvBusy(true);
    try {
      const cleanId = uvId.trim();
      if (typeof window !== "undefined") {
        window.localStorage.setItem("helpdesk_uv_id", cleanId);
      }
      await api.provideUltraView(ticketId, cleanId, uvPass.trim());
      setUvPass("");
      setShowUvForm(false);
      await loadTicket();
    } finally {
      setUvBusy(false);
    }
  };

  const handleSendReply = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!commentBody.trim() || sending) return;
    setSending(true);
    try {
      await api.addComment(ticketId, {
        body: commentBody,
        is_internal: false,
        attachment_ids: commentAttachments.map((a) => a.id),
      });
      setCommentBody("");
      setCommentAttachments([]);
      setShowUploader(false);
      await loadTicket();
    } finally {
      setSending(false);
    }
  };

  const handlePasteReply = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
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

  const handleStatusChange = async (status: "CANCELLED" | "REOPENED" | "CLOSED") => {
    await api.updateTicketStatus(ticketId, status);
    await loadTicket();
  };

  const handleRate = async (e: React.FormEvent) => {
    e.preventDefault();
    setRatingBusy(true);
    try {
      await api.rateTicket(ticketId, rating, feedback, true);
      await loadTicket();
    } finally {
      setRatingBusy(false);
    }
  };

  return (
    <AppShell fullBleed>
      <div className="h-[calc(100dvh-44px)] grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_300px] overflow-hidden">
        {/* Main Thread + Composer */}
        <section className="flex flex-col min-w-0 bg-card overflow-hidden">
          <div className="h-11 px-4 border-b border-border flex items-center justify-between gap-3 shrink-0">
            <div className="flex items-center gap-2.5 min-w-0">
              <Link
                href="/portal"
                className="inline-flex items-center gap-1 text-meta hover:text-foreground shrink-0"
              >
                <ArrowLeft className="size-4" strokeWidth={1.5} />
                <span>Portal</span>
              </Link>
              <span className="h-3.5 w-px bg-border" />
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
                {ticket.status !== "CLOSED" && ticket.status !== "CANCELLED" && (
                  <Button
                    variant="outline"
                    onClick={() => {
                      setShowUvForm((v) => !v);
                      window.setTimeout(() => uvPassInputRef.current?.focus(), 50);
                    }}
                  >
                    <Monitor className="size-3.5" strokeWidth={1.5} />
                    <span>Share UltraViewer</span>
                  </Button>
                )}
                {ticket.status === "NEW" && (
                  <Button
                    variant="outline"
                    onClick={() => void handleStatusChange("CANCELLED")}
                  >
                    <XCircle className="size-3.5" strokeWidth={1.5} />
                    <span>Cancel ticket</span>
                  </Button>
                )}
                {ticket.status === "RESOLVED" && (
                  <>
                    <Button
                      variant="outline"
                      onClick={() => void handleStatusChange("REOPENED")}
                    >
                      <RotateCcw className="size-3.5" strokeWidth={1.5} />
                      <span>Reopen</span>
                    </Button>
                    <Button
                      variant="primary"
                      onClick={() => void handleStatusChange("CLOSED")}
                    >
                      <span>Close ticket</span>
                    </Button>
                  </>
                )}
              </div>
            )}
          </div>

          <div className="flex-1 overflow-y-auto px-4 py-4">
            {loading || !ticket ? (
              <div className="max-w-[760px] rounded-lg border border-border bg-card overflow-hidden">
                <SkeletonRow count={3} compact />
              </div>
            ) : (
              <div className="max-w-[760px] space-y-5">
                {/* Original description (no bubble) */}
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
                          className="rounded-sm border border-border overflow-hidden"
                        >
                          {att.content_type.startsWith("image/") ? (
                            <img
                              src={buildAttachmentUrl(att.download_url)}
                              alt={att.file_name}
                              className="h-24 w-auto object-cover"
                            />
                          ) : (
                            <span className="px-2.5 py-1.5 text-[13px] inline-block">
                              {att.file_name}
                            </span>
                          )}
                        </a>
                      ))}
                    </div>
                  )}
                </div>

                {/* Rating prompt when RESOLVED */}
                {ticket.status === "RESOLVED" && (
                  <form
                    onSubmit={handleRate}
                    className="rounded-md border border-border bg-background p-4 space-y-3"
                  >
                    <p className="text-body-strong">Rate support quality and close ticket</p>
                    <div className="flex items-center gap-1">
                      {[1, 2, 3, 4, 5].map((star) => (
                        <button
                          key={star}
                          type="button"
                          onClick={() => setRating(star)}
                          className="p-1 rounded-xs hover:bg-muted"
                        >
                          <Star
                            className={`size-4 ${
                              star <= rating
                                ? "text-[var(--priority-high)]"
                                : "text-faint"
                            }`}
                            strokeWidth={1.5}
                          />
                        </button>
                      ))}
                      <span className="text-meta tabular-nums ml-2">{rating}/5</span>
                    </div>
                    <input
                      type="text"
                      value={feedback}
                      onChange={(e) => setFeedback(e.target.value)}
                      placeholder="Optional feedback..."
                      className={inputBaseClass}
                    />
                    <Button type="submit" variant="primary" disabled={ratingBusy}>
                      Submit rating
                    </Button>
                  </form>
                )}

                {/* Comments Stream (no bubbles) */}
                {ticket.comments.map((c) => (
                  <div key={c.id} className="anim-fade-up">
                    <div className="flex items-center gap-2">
                      <Avatar name={c.author.full_name} />
                      <span className="text-body-strong">{c.author.full_name}</span>
                      <span className="text-meta-faint tabular-nums">
                        {formatRelativeTime(c.created_at)}
                      </span>
                    </div>
                    <p className="pl-8 mt-1 text-body whitespace-pre-wrap">{c.body}</p>
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
                ))}
              </div>
            )}
          </div>

          {ticket && ticket.status !== "CLOSED" && ticket.status !== "CANCELLED" && (
            <div className="px-4 pb-4 pt-2 border-t border-border-subtle bg-card shrink-0 space-y-2">
              {(showUvForm || ticket.custom_data?.ultraview?.state === "REQUESTED") && (
                <form
                  onSubmit={handleProvideUv}
                  className="anim-fade-up max-w-[760px] rounded-md border border-border bg-background p-3 space-y-2"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="inline-flex items-center gap-1.5 text-body-strong">
                      <Monitor className="size-4 text-[var(--action-reply)]" strokeWidth={1.5} />
                      <span>
                        {ticket.custom_data?.ultraview?.requested_by
                          ? `${ticket.custom_data.ultraview.requested_by} cần kết nối UltraViewer vào máy của bạn`
                          : "Gửi thông tin kết nối UltraViewer"}
                      </span>
                    </span>
                    {ticket.custom_data?.ultraview?.state !== "REQUESTED" && (
                      <button
                        type="button"
                        onClick={() => setShowUvForm(false)}
                        className="text-meta hover:text-foreground"
                      >
                        Close
                      </button>
                    )}
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-[1fr_140px_auto] gap-2">
                    <input
                      type="text"
                      required
                      value={uvId}
                      onChange={(e) => setUvId(e.target.value)}
                      placeholder="UltraViewer ID (VD: 68 412 903)"
                      className={`${inputBaseClass} font-mono tabular-nums`}
                    />
                    <input
                      ref={uvPassInputRef}
                      type="text"
                      required
                      value={uvPass}
                      onChange={(e) => setUvPass(e.target.value)}
                      placeholder="Pass (VD: 8492)"
                      className={`${inputBaseClass} font-mono tabular-nums`}
                    />
                    <Button type="submit" variant="primary" disabled={uvBusy}>
                      Send UltraViewer
                    </Button>
                  </div>
                </form>
              )}

              <form
                onSubmit={handleSendReply}
                className="max-w-[760px] rounded-md border border-border bg-card p-4 space-y-2"
              >
                {ticket.status === "WAITING_FOR_USER" && (
                  <p className="text-meta">
                    IT is waiting for your reply. Sending a message resumes work automatically.
                  </p>
                )}
                <textarea
                  rows={3}
                  value={commentBody}
                  onChange={(e) => setCommentBody(e.target.value)}
                  onPaste={handlePasteReply}
                  placeholder="Write a message… (Ctrl+V to paste screenshot)"
                  className="w-full resize-none bg-transparent text-body placeholder:text-faint focus:outline-none"
                />

                {(showUploader || commentAttachments.length > 0) && (
                  <PasteImageUploader
                    ref={uploaderRef}
                    ticketId={ticket.id}
                    attachments={commentAttachments}
                    onChange={setCommentAttachments}
                    compact
                  />
                )}

                <div className="flex items-center justify-between pt-2">
                  <button
                    type="button"
                    onClick={() => setShowUploader((v) => !v)}
                    className="text-faint hover:text-foreground transition-colors duration-75"
                    title="Attach file"
                  >
                    <Paperclip className="size-4" strokeWidth={1.5} />
                  </button>

                  <Button
                    type="submit"
                    variant="primary"
                    disabled={!commentBody.trim() || sending}
                  >
                    <Send className="size-3.5" strokeWidth={1.5} />
                    <span>Send reply</span>
                  </Button>
                </div>
              </form>
            </div>
          )}
        </section>

        {/* Right Properties Panel (300px) */}
        <aside className="hidden lg:block border-l border-border bg-background overflow-y-auto p-4">
          {ticket && (
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
                  <div className="flex items-center gap-1.5 text-body">
                    <PriorityGlyph priority={ticket.priority} />
                    <span>{PRIORITY_LABELS[ticket.priority]}</span>
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
                {ticket.asset_code && (
                  <div className="grid grid-cols-[96px_minmax(0,1fr)] items-center gap-x-3 min-h-[32px]">
                    <span className="text-meta">Asset Code</span>
                    <div>
                      <TopicBadge label={ticket.asset_code} iconSlug="asset" mono />
                    </div>
                  </div>
                )}
                <div className="grid grid-cols-[96px_minmax(0,1fr)] items-center gap-x-3 min-h-[32px]">
                  <span className="text-meta">Assignee</span>
                  <span className={ticket.assignee ? "text-body truncate" : "text-body text-faint truncate"}>
                    {ticket.assignee?.full_name || "Unassigned"}
                  </span>
                </div>
                {ticket.status !== "CANCELLED" && ticket.status !== "CLOSED" && (
                  <div className="grid grid-cols-[96px_minmax(0,1fr)] items-center gap-x-3 min-h-[32px]">
                    <span className="text-meta">Due at</span>
                    <span className="text-body tabular-nums">
                      {formatDateTime(ticket.resolution_due_at)}
                    </span>
                  </div>
                )}
                <div className="grid grid-cols-[96px_minmax(0,1fr)] items-center gap-x-3 min-h-[32px]">
                  <span className="text-meta">UltraViewer</span>
                  <span className="text-body font-mono tabular-nums truncate">
                    {ticket.custom_data?.ultraview?.id
                      ? formatUltraViewId(ticket.custom_data.ultraview.id)
                      : "—"}
                  </span>
                </div>
              </div>

              <div className="border-t border-border pt-4 space-y-3">
                <p className="text-meta">Timeline</p>
                <TicketTimeline events={ticket.timeline} />
              </div>
            </div>
          )}
        </aside>
      </div>
    </AppShell>
  );
}
