"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { BookOpen, Check, ExternalLink, Lock, Sparkles, X } from "lucide-react";

import { useNavigationProgress } from "@/components/NavigationProgress";
import {
  PasteImageUploader,
  PasteUploaderHandle,
} from "@/components/PasteImageUploader";
import { Button, inputBaseClass, selectBaseClass } from "@/components/ui/primitives";
import { api, buildAttachmentUrl } from "@/lib/api";
import { cn } from "@/lib/cn";
import { Attachment, Category, KbArticleDetail, KbVisibility, TicketDetail } from "@/lib/types";

export function SaveTicketToKbModal({
  open,
  onClose,
  ticket,
  categories,
}: {
  open: boolean;
  onClose: () => void;
  ticket: TicketDetail;
  categories: Category[];
}) {
  const { startNavigation } = useNavigationProgress();
  const uploaderRef = useRef<PasteUploaderHandle | null>(null);

  const [title, setTitle] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [visibility, setVisibility] = useState<KbVisibility>("INTERNAL");
  const [symptoms, setSymptoms] = useState("");
  const [rootCause, setRootCause] = useState("");
  const [stepsText, setStepsText] = useState("");
  const [notes, setNotes] = useState("");
  const [keywords, setKeywords] = useState("");
  const [selectedExistingIds, setSelectedExistingIds] = useState<Set<string>>(new Set());
  const [newAttachments, setNewAttachments] = useState<Attachment[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedArticle, setSavedArticle] = useState<KbArticleDetail | null>(null);

  const existingTicketAttachments = useMemo(() => {
    const map = new Map<string, Attachment>();
    for (const att of ticket.attachments || []) {
      map.set(att.id, att);
    }
    for (const c of ticket.comments || []) {
      for (const att of c.attachments || []) {
        map.set(att.id, att);
      }
    }
    return Array.from(map.values());
  }, [ticket]);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setSavedArticle(null);
    setTitle(ticket.title);
    setCategoryId(ticket.category_id || "");
    setVisibility("INTERNAL");
    setSymptoms(ticket.description);
    setRootCause("");

    const latestItComment = [...(ticket.comments || [])]
      .reverse()
      .find((c) => c.author_id !== ticket.requester_id);
    setStepsText(latestItComment ? latestItComment.body : "");
    setNotes("");
    setKeywords(ticket.category?.slug ? ticket.category.slug.replace(/-/g, ", ") : "");
    setSelectedExistingIds(new Set());
    setNewAttachments([]);
  }, [open, ticket]);

  if (!open) return null;

  const toggleExisting = (id: string) => {
    setSelectedExistingIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || saving) return;

    setSaving(true);
    setError(null);
    try {
      const steps = stepsText
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean);
      const kwList = keywords
        .split(",")
        .map((k) => k.trim())
        .filter(Boolean);
      const attachmentIds = [
        ...Array.from(selectedExistingIds),
        ...newAttachments.map((a) => a.id),
      ];

      const created = await api.createKbArticle({
        title: title.trim(),
        category_id: categoryId || null,
        visibility,
        symptoms: symptoms.trim() || null,
        root_cause: rootCause.trim() || null,
        steps,
        notes: notes.trim() || null,
        keywords: kwList,
        source_ticket_id: ticket.id,
        attachment_ids: attachmentIds,
      });
      setSavedArticle(created);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Lưu Knowledge Base thất bại.");
    } finally {
      setSaving(false);
    }
  };

  const handleModalPaste = (e: React.ClipboardEvent) => {
    const items = Array.from(e.clipboardData?.items || []);
    const files = items
      .filter((it) => it.kind === "file")
      .map((it) => it.getAsFile())
      .filter((f): f is File => Boolean(f));
    if (files.length > 0) {
      e.preventDefault();
      void uploaderRef.current?.uploadFiles(files);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Save ticket solution to Knowledge Base"
      onClick={onClose}
      className="anim-scrim fixed inset-0 z-50 bg-[var(--scrim)] backdrop-blur-[2px] flex items-center justify-center p-4"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        onPaste={handleModalPaste}
        className="anim-popover w-full max-w-[680px] max-h-[90dvh] rounded-xl border border-border bg-card shadow-popover overflow-hidden flex flex-col"
      >
        <div className="h-11 px-4 border-b border-border flex items-center justify-between gap-3 shrink-0 bg-background">
          <div className="flex items-center gap-2">
            <BookOpen className="size-4 text-muted-foreground" strokeWidth={1.5} />
            <span className="text-body-strong">Save to Knowledge Base</span>
            <span className="text-meta font-mono tabular-nums">{ticket.ticket_code}</span>
          </div>
          <Button type="button" variant="icon" onClick={onClose} aria-label="Close">
            <X className="size-4" strokeWidth={1.5} />
          </Button>
        </div>

        {savedArticle ? (
          <div className="p-6 space-y-4">
            <div className="rounded-md border border-[#CBEBD9] bg-[#F1FAF5] px-4 py-3 text-[13px] text-[#14532D] flex items-start gap-2.5">
              <Check className="size-4 shrink-0 mt-0.5" strokeWidth={2} />
              <div>
                <p className="font-medium">Saved &ldquo;{savedArticle.title}&rdquo; to Knowledge Base.</p>
                <p className="mt-0.5 text-[12px] opacity-90">
                  Stored in database and linked back to {ticket.ticket_code}.
                </p>
              </div>
            </div>

            <div className="flex items-center justify-end gap-2">
              <Button type="button" variant="outline" onClick={onClose}>
                Close
              </Button>
              <Link
                href={`/workspace/kb?id=${savedArticle.id}`}
                onClick={() => {
                  startNavigation(`/workspace/kb?id=${savedArticle.id}`);
                  onClose();
                }}
                className="inline-flex h-8 items-center gap-1.5 rounded-sm bg-primary px-3 text-[13px] font-medium text-primary-foreground hover:opacity-90"
              >
                <span>Open in Knowledge Base</span>
                <ExternalLink className="size-3.5" strokeWidth={1.5} />
              </Link>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSave} className="flex flex-col min-h-0 flex-1">
            <div className="flex-1 overflow-y-auto p-4 space-y-3.5">
              {error && (
                <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-[13px] text-destructive">
                  {error}
                </div>
              )}

              <div className="space-y-1">
                <label className="block text-meta">Guide title</label>
                <input
                  type="text"
                  required
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className={inputBaseClass}
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="block text-meta">Category</label>
                  <select
                    value={categoryId}
                    onChange={(e) => setCategoryId(e.target.value)}
                    className={cn(selectBaseClass, "w-full h-9")}
                  >
                    <option value="">General</option>
                    {categories.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="space-y-1">
                  <label className="block text-meta">Visibility</label>
                  <div className="grid grid-cols-2 gap-1.5 h-9 p-0.5 rounded-md border border-input bg-background">
                    <button
                      type="button"
                      onClick={() => setVisibility("INTERNAL")}
                      className={cn(
                        "rounded-sm text-[13px] font-medium inline-flex items-center justify-center gap-1.5",
                        visibility === "INTERNAL"
                          ? "bg-card text-foreground border border-border"
                          : "text-muted-foreground hover:text-foreground"
                      )}
                    >
                      <Lock className="size-3.5" strokeWidth={1.5} />
                      <span>IT Runbook</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setVisibility("PUBLIC")}
                      className={cn(
                        "rounded-sm text-[13px] font-medium inline-flex items-center justify-center gap-1.5",
                        visibility === "PUBLIC"
                          ? "bg-card text-foreground border border-border"
                          : "text-muted-foreground hover:text-foreground"
                      )}
                    >
                      <Sparkles className="size-3.5" strokeWidth={1.5} />
                      <span>Self-Help</span>
                    </button>
                  </div>
                </div>
              </div>

              <div className="space-y-1">
                <label className="block text-meta">Symptoms</label>
                <textarea
                  rows={2}
                  value={symptoms}
                  onChange={(e) => setSymptoms(e.target.value)}
                  className={inputBaseClass}
                />
              </div>

              <div className="space-y-1">
                <label className="block text-meta">Root cause (optional)</label>
                <input
                  type="text"
                  value={rootCause}
                  onChange={(e) => setRootCause(e.target.value)}
                  placeholder="Nguyên nhân gốc rễ..."
                  className={inputBaseClass}
                />
              </div>

              <div className="space-y-1">
                <label className="block text-meta">
                  Fix steps (one step per line)
                </label>
                <textarea
                  rows={4}
                  value={stepsText}
                  onChange={(e) => setStepsText(e.target.value)}
                  placeholder="Các bước xử lý..."
                  className={inputBaseClass}
                />
              </div>

              <div className="space-y-1">
                <label className="block text-meta">
                  Commands / Technical notes (optional)
                </label>
                <textarea
                  rows={2}
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Lệnh PowerShell, CMD hoặc ghi chú kỹ thuật..."
                  className={cn(inputBaseClass, "font-mono text-[13px]")}
                />
              </div>

              <div className="space-y-1">
                <label className="block text-meta">Keywords (comma-separated)</label>
                <input
                  type="text"
                  value={keywords}
                  onChange={(e) => setKeywords(e.target.value)}
                  placeholder="vpn, printer, erp..."
                  className={inputBaseClass}
                />
              </div>

              {existingTicketAttachments.length > 0 && (
                <div className="space-y-1.5">
                  <label className="block text-meta">
                    Copy images/files from this ticket ({selectedExistingIds.size} selected)
                  </label>
                  <div className="flex flex-wrap gap-2">
                    {existingTicketAttachments.map((att) => {
                      const picked = selectedExistingIds.has(att.id);
                      const isImg = att.content_type.startsWith("image/");
                      return (
                        <button
                          key={att.id}
                          type="button"
                          onClick={() => toggleExisting(att.id)}
                          className={cn(
                            "flex items-center gap-2 rounded-sm border p-1.5 pr-2.5 text-[12px] transition-colors duration-75",
                            picked
                              ? "border-foreground bg-muted text-foreground"
                              : "border-border bg-card text-muted-foreground hover:text-foreground"
                          )}
                        >
                          {isImg && (
                            <img
                              src={buildAttachmentUrl(att.download_url)}
                              alt={att.file_name}
                              className="size-8 object-cover rounded-xs border border-border-subtle"
                            />
                          )}
                          <span className="max-w-[140px] truncate">{att.file_name}</span>
                          {picked && <Check className="size-3.5 shrink-0" strokeWidth={2} />}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

              <div className="space-y-1.5">
                <label className="block text-meta">
                  Add new screenshots (Ctrl+V directly)
                </label>
                <PasteImageUploader
                  ref={uploaderRef}
                  attachments={newAttachments}
                  onChange={setNewAttachments}
                  compact
                />
              </div>
            </div>

            <div className="px-4 py-3 border-t border-border bg-background flex items-center justify-end gap-2 shrink-0">
              <Button type="button" variant="outline" onClick={onClose}>
                Cancel
              </Button>
              <Button type="submit" variant="primary" disabled={!title.trim() || saving}>
                {saving ? "Saving..." : "Save to Knowledge Base"}
              </Button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
