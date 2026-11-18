"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { BookOpen, Check, ChevronDown, ChevronRight, Inbox, Loader2, Send } from "lucide-react";

import { AppShell } from "@/components/AppShell";
import {
  PasteImageUploader,
  PasteUploaderHandle,
} from "@/components/PasteImageUploader";
import {
  Button,
  PriorityGlyph,
  SkeletonRow,
  SlaBadge,
  TopicBadge,
  inputBaseClass,
  selectBaseClass,
} from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import {
  formatRelativeTime,
  PRIORITY_LABELS,
  STATUS_LABELS,
} from "@/lib/formatters";
import { Attachment, Category, KbArticle, Ticket, TicketPriority } from "@/lib/types";
import { useRealtime } from "@/lib/use-realtime";

export default function EmployeePortalPage() {
  const router = useRouter();
  const [categories, setCategories] = useState<Category[]>([]);
  const [myTickets, setMyTickets] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState(true);

  const [selectedCategoryId, setSelectedCategoryId] = useState<string>("");
  const [priority, setPriority] = useState<TicketPriority>("MEDIUM");
  const [title, setTitle] = useState("");
  const [assetCode, setAssetCode] = useState("");
  const [uvId, setUvId] = useState("");
  const [uvPass, setUvPass] = useState("");
  const [description, setDescription] = useState("");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [expandedKbId, setExpandedKbId] = useState<string | null>(null);
  const [feedbackMsg, setFeedbackMsg] = useState<{
    type: "ok" | "err";
    text: string;
  } | null>(null);

  const uploaderRef = useRef<PasteUploaderHandle | null>(null);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const savedUvId = window.localStorage.getItem("helpdesk_uv_id");
      if (savedUvId) setUvId(savedUvId);
    }
  }, []);

  const loadData = useCallback(async () => {
    try {
      const [meta, list] = await Promise.all([
        api.getMetadata(),
        api.listTickets({ limit: 50 }),
      ]);
      setCategories(meta.categories);
      if (meta.categories.length > 0 && !selectedCategoryId) {
        setSelectedCategoryId(meta.categories[0].id);
        setPriority(meta.categories[0].default_priority);
      }
      setMyTickets(list.items);
    } finally {
      setLoading(false);
    }
  }, [selectedCategoryId]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  useRealtime(() => {
    void loadData();
  });

  const handleCategorySelect = (cat: Category) => {
    setSelectedCategoryId(cat.id);
    setPriority(cat.default_priority);
  };

  const suggestedKbArticles = useMemo(() => {
    const query = `${title} ${description}`.trim().toLowerCase();
    const seen = new Set<string>();
    const results: Array<{ categoryName: string; article: KbArticle }> = [];

    // 1. Keyword matches across all categories when user types
    if (query.length >= 2) {
      for (const cat of categories) {
        const list = cat.form_schema?.kb_articles || [];
        for (const art of list) {
          const hit =
            art.title.toLowerCase().includes(query) ||
            art.keywords.some((kw) => query.includes(kw.toLowerCase()));
          if (hit && !seen.has(art.id)) {
            seen.add(art.id);
            results.push({ categoryName: cat.name, article: art });
          }
        }
      }
    }

    // 2. Fallback / supplement from selected category
    const selectedCat = categories.find((c) => c.id === selectedCategoryId);
    if (selectedCat) {
      for (const art of selectedCat.form_schema?.kb_articles || []) {
        if (!seen.has(art.id)) {
          seen.add(art.id);
          results.push({ categoryName: selectedCat.name, article: art });
        }
      }
    }

    return results.slice(0, 3);
  }, [categories, selectedCategoryId, title, description]);

  const handleSelfSolved = () => {
    setTitle("");
    setDescription("");
    setAssetCode("");
    setUvPass("");
    setAttachments([]);
    setExpandedKbId(null);
    setFeedbackMsg({
      type: "ok",
      text: "Glad the guide helped! No ticket was needed.",
    });
  };

  const handleDescriptionPaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFeedbackMsg(null);
    setSubmitting(true);
    try {
      const cleanUvId = uvId.trim();
      if (cleanUvId && typeof window !== "undefined") {
        window.localStorage.setItem("helpdesk_uv_id", cleanUvId);
      }
      const created = await api.createTicket({
        title,
        description,
        category_id: selectedCategoryId || null,
        priority,
        asset_code: assetCode.trim() || undefined,
        ultraview_id: cleanUvId || undefined,
        ultraview_pass: uvPass.trim() || undefined,
        attachment_ids: attachments.map((a) => a.id),
      });
      setTitle("");
      setDescription("");
      setAssetCode("");
      setUvPass("");
      setAttachments([]);
      setFeedbackMsg({
        type: "ok",
        text: `Created ticket ${created.ticket_code}. IT team has been notified.`,
      });
      await loadData();
    } catch (err: unknown) {
      setFeedbackMsg({
        type: "err",
        text: err instanceof Error ? err.message : "Could not create ticket.",
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AppShell>
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
        {/* Left: Quick Ticket Form */}
        <section className="lg:col-span-5 rounded-lg border border-border bg-card p-4 space-y-4">
          <div className="border-b border-border-subtle pb-3">
            <h1 className="text-[17px] leading-[22px] font-medium text-foreground">
              New support ticket
            </h1>
            <p className="text-meta mt-0.5">
              10-second submission — press Ctrl+V to paste screenshots directly.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-3">
            <div className="space-y-1.5">
              <label className="block text-meta">Category</label>
              <div className="grid grid-cols-2 gap-1.5">
                {categories.map((cat) => {
                  const active = cat.id === selectedCategoryId;
                  return (
                    <button
                      key={cat.id}
                      type="button"
                      onClick={() => handleCategorySelect(cat)}
                      className={cn(
                        "text-left px-2.5 py-2 rounded-sm border text-[13px] leading-[18px] transition-colors duration-75 truncate",
                        active
                          ? "bg-muted border-foreground/40 text-foreground font-medium"
                          : "bg-card border-border text-muted-foreground hover:bg-muted/60 hover:text-foreground"
                      )}
                    >
                      {cat.name}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="space-y-1">
              <label className="block text-meta">Title</label>
              <input
                type="text"
                required
                minLength={3}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Brief summary of the issue"
                className={inputBaseClass}
              />
            </div>

            {suggestedKbArticles.length > 0 && (
              <div className="anim-fade-up rounded-md border border-border bg-background p-3 space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="inline-flex items-center gap-1.5 text-meta text-foreground font-medium">
                    <BookOpen className="size-3.5 text-muted-foreground" strokeWidth={1.5} />
                    <span>Suggested self-help</span>
                  </span>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={handleSelfSolved}
                  >
                    <Check className="size-3" strokeWidth={1.5} />
                    <span>Solved — no ticket needed</span>
                  </Button>
                </div>

                <div className="divide-y divide-border-subtle rounded-sm border border-border bg-card overflow-hidden">
                  {suggestedKbArticles.map(({ article }) => {
                    const isOpen = expandedKbId === article.id;
                    return (
                      <div key={article.id}>
                        <button
                          type="button"
                          onClick={() =>
                            setExpandedKbId(isOpen ? null : article.id)
                          }
                          className="w-full px-3 py-2 flex items-center justify-between gap-2 text-left hover:bg-muted/60 transition-colors duration-75"
                        >
                          <span className="text-[13px] font-medium text-foreground truncate">
                            {article.title}
                          </span>
                          {isOpen ? (
                            <ChevronDown className="size-3.5 text-muted-foreground shrink-0" strokeWidth={1.5} />
                          ) : (
                            <ChevronRight className="size-3.5 text-muted-foreground shrink-0" strokeWidth={1.5} />
                          )}
                        </button>
                        {isOpen && (
                          <ol className="px-3 pb-2.5 pt-1 space-y-1 border-t border-border-subtle bg-card text-[13px] leading-[18px] text-muted-foreground list-decimal list-inside">
                            {article.steps.map((step, i) => (
                              <li key={i}>{step}</li>
                            ))}
                          </ol>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <label className="block text-meta">Asset code (optional)</label>
                <input
                  type="text"
                  value={assetCode}
                  onChange={(e) => setAssetCode(e.target.value)}
                  placeholder="PC-KT-012"
                  className={cn(inputBaseClass, "font-mono")}
                />
              </div>

              <div className="space-y-1">
                <label className="block text-meta">Priority</label>
                <select
                  value={priority}
                  onChange={(e) => setPriority(e.target.value as TicketPriority)}
                  className={cn(selectBaseClass, "w-full h-[36px] text-[15px]")}
                >
                  <option value="LOW">Low</option>
                  <option value="MEDIUM">Medium</option>
                  <option value="HIGH">High</option>
                  <option value="CRITICAL">Urgent</option>
                </select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <label className="block text-meta">UltraViewer ID (optional)</label>
                <input
                  type="text"
                  value={uvId}
                  onChange={(e) => setUvId(e.target.value)}
                  placeholder="68 412 903"
                  className={cn(inputBaseClass, "font-mono tabular-nums")}
                />
              </div>

              <div className="space-y-1">
                <label className="block text-meta">UV Pass (optional)</label>
                <input
                  type="text"
                  value={uvPass}
                  onChange={(e) => setUvPass(e.target.value)}
                  placeholder="8492"
                  className={cn(inputBaseClass, "font-mono tabular-nums")}
                />
              </div>
            </div>

            <div className="space-y-1">
              <label className="block text-meta">
                Description (Ctrl+V to paste screenshot)
              </label>
              <textarea
                required
                rows={4}
                minLength={3}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                onPaste={handleDescriptionPaste}
                placeholder="Describe what happened..."
                className={inputBaseClass}
              />
            </div>

            <PasteImageUploader
              ref={uploaderRef}
              attachments={attachments}
              onChange={setAttachments}
              compact
            />

            {feedbackMsg && (
              <div
                className={cn(
                  "rounded-md border px-3 py-2 text-[13px] flex items-center gap-2",
                  feedbackMsg.type === "ok"
                    ? "border-border bg-muted text-foreground"
                    : "border-destructive/30 bg-destructive/5 text-destructive"
                )}
              >
                {feedbackMsg.type === "ok" && (
                  <Check className="size-3.5 shrink-0" strokeWidth={1.75} />
                )}
                <span>{feedbackMsg.text}</span>
              </div>
            )}

            <Button type="submit" disabled={submitting} className="w-full">
              {submitting ? (
                <Loader2 className="size-3.5 animate-spin" strokeWidth={1.5} />
              ) : (
                <Send className="size-3.5" strokeWidth={1.5} />
              )}
              <span>Create ticket</span>
            </Button>
          </form>
        </section>

        {/* Right: My Tickets Table */}
        <section className="lg:col-span-7 rounded-lg border border-border bg-card overflow-hidden">
          <div className="h-11 px-4 border-b border-border flex items-center justify-between bg-background">
            <h2 className="text-body-strong">My tickets</h2>
            <span className="text-meta tabular-nums">{myTickets.length}</span>
          </div>

          <div className="hidden sm:grid grid-cols-[88px_minmax(0,1fr)_120px] items-center gap-x-4 h-8 px-4 border-b border-border-subtle text-meta bg-card">
            <span>SLA</span>
            <span>Topic</span>
            <span>Assignee</span>
          </div>

          {loading ? (
            <SkeletonRow count={4} compact />
          ) : myTickets.length === 0 ? (
            <div className="px-4 py-8 flex flex-col items-start gap-2">
              <Inbox className="size-5 text-faint" strokeWidth={1.5} />
              <p className="text-body">
                No tickets submitted yet. Use the form on the left to send your first request.
              </p>
            </div>
          ) : (
            <div>
              {myTickets.map((t) => (
                <div
                  key={t.id}
                  role="row"
                  tabIndex={0}
                  onClick={() => router.push(`/portal/tickets/${t.id}`)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") router.push(`/portal/tickets/${t.id}`);
                  }}
                  className="cursor-pointer grid grid-cols-1 sm:grid-cols-[88px_minmax(0,1fr)_120px] items-start gap-x-4 gap-y-2 px-4 py-3 min-h-[72px] border-b border-border-subtle last:border-b-0 bg-card hover:bg-muted/60 transition-colors duration-75"
                >
                  <div className="pt-[1px]">
                    <SlaBadge ticket={t} />
                  </div>

                  <div className="min-w-0">
                    <div className="flex items-center gap-2 min-w-0">
                      <PriorityGlyph priority={t.priority} />
                      <span className="text-meta font-mono tabular-nums shrink-0">
                        {t.ticket_code}
                      </span>
                      <span className="text-body-strong truncate">{t.title}</span>
                    </div>
                    <div className="mt-1.5 flex items-center gap-2 overflow-hidden">
                      {t.category && (
                        <TopicBadge
                          label={t.category.name}
                          iconSlug={t.category.slug}
                        />
                      )}
                      {t.asset_code && (
                        <TopicBadge
                          label={t.asset_code}
                          iconSlug="asset"
                          mono
                        />
                      )}
                      <TopicBadge label={STATUS_LABELS[t.status]} iconSlug="tag" />
                    </div>
                  </div>

                  <div className="text-right sm:text-left">
                    <p className="text-meta truncate">
                      {t.assignee ? t.assignee.full_name : PRIORITY_LABELS[t.priority]}
                    </p>
                    <p className="text-meta-faint tabular-nums">
                      {formatRelativeTime(t.created_at)}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </AppShell>
  );
}
