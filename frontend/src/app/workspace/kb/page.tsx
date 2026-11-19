"use client";

import React, { Suspense, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  BookOpen,
  Check,
  Copy,
  Edit3,
  ExternalLink,
  FileText,
  Image as ImageIcon,
  Lock,
  Plus,
  Search,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";

import { AppShell } from "@/components/AppShell";
import { useNavigationProgress } from "@/components/NavigationProgress";
import {
  PasteImageUploader,
  PasteUploaderHandle,
} from "@/components/PasteImageUploader";
import {
  Button,
  SkeletonRow,
  TopicBadge,
  inputBaseClass,
  selectBaseClass,
} from "@/components/ui/primitives";
import { api, buildAttachmentUrl } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { cn } from "@/lib/cn";
import { formatDateTime, formatRelativeTime, isItRole } from "@/lib/formatters";
import { Attachment, Category, KbArticleDetail, KbVisibility } from "@/lib/types";

function VisibilityBadge({ visibility }: { visibility: KbVisibility }) {
  const isInternal = visibility === "INTERNAL";
  return (
    <span
      className={cn(
        "inline-flex h-6 items-center gap-1.5 rounded-sm border px-2 text-[12px] font-medium leading-4 whitespace-nowrap shrink-0",
        isInternal
          ? "border-note-border bg-note text-note-ink"
          : "border-[#D5E2FA] bg-[#F5F8FF] text-[#1E3A8A]"
      )}
    >
      {isInternal ? (
        <Lock className="size-3 shrink-0" strokeWidth={1.75} />
      ) : (
        <Sparkles className="size-3 shrink-0" strokeWidth={1.75} />
      )}
      <span>{isInternal ? "IT Runbook" : "Self-Help"}</span>
    </span>
  );
}

function KnowledgeBaseContent() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { startNavigation } = useNavigationProgress();

  const [articles, setArticles] = useState<KbArticleDetail[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [visFilter, setVisFilter] = useState<KbVisibility | "">("");
  const [catFilter, setCatFilter] = useState("");

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [mobileShowDetail, setMobileShowDetail] = useState(false);

  // Editor state
  const [mode, setMode] = useState<"view" | "create" | "edit">("view");
  const [formTitle, setFormTitle] = useState("");
  const [formCategoryId, setFormCategoryId] = useState("");
  const [formVisibility, setFormVisibility] = useState<KbVisibility>("INTERNAL");
  const [formSymptoms, setFormSymptoms] = useState("");
  const [formRootCause, setFormRootCause] = useState("");
  const [formStepsText, setFormStepsText] = useState("");
  const [formNotes, setFormNotes] = useState("");
  const [formKeywords, setFormKeywords] = useState("");
  const [formAttachments, setFormAttachments] = useState<Attachment[]>([]);
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [lightboxUrl, setLightboxUrl] = useState<{ url: string; name: string } | null>(null);

  const uploaderRef = useRef<PasteUploaderHandle | null>(null);

  useEffect(() => {
    if (!authLoading && user && !isItRole(user.role)) {
      startNavigation("/portal");
      router.replace("/portal");
    }
  }, [authLoading, user, router, startNavigation]);

  const loadData = useCallback(async () => {
    setError(null);
    try {
      const [kbRes, meta] = await Promise.all([
        api.listKbArticles({
          q: search.trim() || undefined,
          visibility: visFilter || undefined,
          category_id: catFilter || undefined,
        }),
        api.getMetadata(),
      ]);
      setArticles(kbRes.items);
      setCategories(meta.categories);

      const urlId = searchParams?.get("id");
      setSelectedId((prev) => {
        if (urlId && kbRes.items.some((a) => a.id === urlId)) return urlId;
        if (prev && kbRes.items.some((a) => a.id === prev)) return prev;
        return kbRes.items[0]?.id ?? null;
      });
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Không thể tải danh sách Knowledge Base."
      );
    } finally {
      setLoading(false);
    }
  }, [search, visFilter, catFilter, searchParams]);

  useEffect(() => {
    if (user && isItRole(user.role)) {
      void loadData();
    }
  }, [user, loadData]);

  const selectedArticle =
    articles.find((a) => a.id === selectedId) ?? null;

  const openCreateMode = () => {
    setMode("create");
    setMobileShowDetail(true);
    setConfirmDelete(false);
    setFormTitle("");
    setFormCategoryId(categories[0]?.id || "");
    setFormVisibility("INTERNAL");
    setFormSymptoms("");
    setFormRootCause("");
    setFormStepsText("");
    setFormNotes("");
    setFormKeywords("");
    setFormAttachments([]);
  };

  const openEditMode = (article: KbArticleDetail) => {
    setMode("edit");
    setMobileShowDetail(true);
    setConfirmDelete(false);
    setFormTitle(article.title);
    setFormCategoryId(article.category_id || "");
    setFormVisibility(article.visibility);
    setFormSymptoms(article.symptoms || "");
    setFormRootCause(article.root_cause || "");
    setFormStepsText((article.steps || []).join("\n"));
    setFormNotes(article.notes || "");
    setFormKeywords((article.keywords || []).join(", "));
    setFormAttachments(article.attachments || []);
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formTitle.trim() || saving) return;

    const steps = formStepsText
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    const keywords = formKeywords
      .split(",")
      .map((k) => k.trim())
      .filter(Boolean);

    setSaving(true);
    setError(null);
    try {
      const payload = {
        title: formTitle.trim(),
        category_id: formCategoryId || null,
        visibility: formVisibility,
        symptoms: formSymptoms.trim() || null,
        root_cause: formRootCause.trim() || null,
        steps,
        notes: formNotes.trim() || null,
        keywords,
        attachment_ids: formAttachments.map((a) => a.id),
      };

      const saved =
        mode === "edit" && selectedArticle
          ? await api.updateKbArticle(selectedArticle.id, payload)
          : await api.createKbArticle(payload);

      setMode("view");
      setSelectedId(saved.id);
      await loadData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Lưu bài viết thất bại.");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!selectedArticle) return;
    setSaving(true);
    try {
      await api.deleteKbArticle(selectedArticle.id);
      setConfirmDelete(false);
      setSelectedId(null);
      setMode("view");
      setMobileShowDetail(false);
      await loadData();
    } finally {
      setSaving(false);
    }
  };

  const handleCopy = async (key: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedKey(key);
      window.setTimeout(() => setCopiedKey(null), 1500);
    } catch {
      // ignore clipboard restrictions
    }
  };

  const handleFormPaste = (e: React.ClipboardEvent) => {
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
    <AppShell fullBleed>
      <div className="h-[calc(100dvh-44px)] grid grid-cols-1 md:grid-cols-[360px_minmax(0,1fr)] overflow-hidden">
        {/* Left Column: Search, Filters & Article List */}
        <aside
          className={cn(
            "border-r border-border bg-background flex flex-col min-h-0",
            mobileShowDetail && "hidden md:flex"
          )}
        >
          <div className="h-11 px-4 border-b border-border flex items-center justify-between shrink-0 bg-background">
            <div className="flex items-center gap-2">
              <BookOpen className="size-4 text-muted-foreground" strokeWidth={1.5} />
              <span className="text-body-strong">Knowledge Base</span>
              <span className="text-meta tabular-nums">{articles.length}</span>
            </div>
            <Button type="button" size="sm" variant="primary" onClick={openCreateMode}>
              <Plus className="size-3.5" strokeWidth={1.75} />
              <span>New tip</span>
            </Button>
          </div>

          <div className="p-3 border-b border-border space-y-2 shrink-0 bg-background">
            <div className="relative">
              <Search
                className="size-4 text-faint absolute left-2.5 top-2"
                strokeWidth={1.5}
              />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search title, symptoms, commands..."
                className="w-full h-8 pl-8 pr-3 rounded-md border border-input bg-card text-[13px] text-foreground placeholder:text-faint focus:outline-none focus:border-foreground/30 focus:ring-2 focus:ring-ring/20"
              />
            </div>

            <div className="flex items-center justify-between gap-2">
              <div className="inline-flex items-center rounded-sm border border-border bg-card p-0.5 text-[12px]">
                {[
                  { id: "" as const, label: "All" },
                  { id: "INTERNAL" as const, label: "IT Runbook" },
                  { id: "PUBLIC" as const, label: "Self-Help" },
                ].map((tab) => (
                  <button
                    key={tab.id || "all"}
                    type="button"
                    onClick={() => setVisFilter(tab.id)}
                    className={cn(
                      "h-6 px-2 rounded-xs font-medium transition-colors duration-75 whitespace-nowrap",
                      visFilter === tab.id
                        ? "bg-muted text-foreground"
                        : "text-muted-foreground hover:text-foreground"
                    )}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>

              <select
                value={catFilter}
                onChange={(e) => setCatFilter(e.target.value)}
                aria-label="Filter by category"
                className={cn(selectBaseClass, "h-7 text-[12px] min-w-0 flex-1")}
              >
                <option value="">All categories</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto">
            {loading ? (
              <SkeletonRow count={5} compact />
            ) : articles.length === 0 ? (
              <div className="p-6 flex flex-col items-start gap-2">
                <BookOpen className="size-5 text-faint" strokeWidth={1.5} />
                <p className="text-body">
                  No KB articles match your filter. Add a new troubleshooting tip to get started.
                </p>
                <Button type="button" variant="outline" size="sm" onClick={openCreateMode}>
                  <Plus className="size-3.5" strokeWidth={1.5} />
                  <span>Create first tip</span>
                </Button>
              </div>
            ) : (
              <div>
                {articles.map((art) => {
                  const isSelected = mode === "view" && selectedId === art.id;
                  const imgCount = art.attachments.filter((a) =>
                    a.content_type.startsWith("image/")
                  ).length;
                  return (
                    <button
                      key={art.id}
                      type="button"
                      onClick={() => {
                        setSelectedId(art.id);
                        setMode("view");
                        setConfirmDelete(false);
                        setMobileShowDetail(true);
                      }}
                      className={cn(
                        "w-full text-left px-4 py-3 border-b border-border-subtle last:border-b-0 bg-card hover:bg-muted/60 transition-colors duration-75 block",
                        isSelected && "bg-muted border-l-2 border-l-foreground"
                      )}
                    >
                      <p className="text-body-strong truncate">{art.title}</p>
                      <div className="mt-1.5 flex items-center justify-between gap-2">
                        <div className="flex items-center gap-1.5 min-w-0 overflow-hidden">
                          <VisibilityBadge visibility={art.visibility} />
                          {art.category && (
                            <TopicBadge
                              label={art.category.name}
                              iconSlug={art.category.slug}
                            />
                          )}
                        </div>
                        <div className="flex items-center gap-2 shrink-0 text-meta-faint tabular-nums">
                          {imgCount > 0 && (
                            <span className="inline-flex items-center gap-0.5">
                              <ImageIcon className="size-3" strokeWidth={1.5} />
                              <span>{imgCount}</span>
                            </span>
                          )}
                          <span>{formatRelativeTime(art.updated_at)}</span>
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </aside>

        {/* Right Column: Article Reader or Create/Edit Editor */}
        <section
          className={cn(
            "flex flex-col min-w-0 min-h-0 bg-card overflow-hidden",
            !mobileShowDetail && "hidden md:flex"
          )}
        >
          {mode === "create" || mode === "edit" ? (
            <form
              onSubmit={handleSave}
              onPaste={handleFormPaste}
              className="flex flex-col h-full min-h-0"
            >
              <div className="h-11 px-4 border-b border-border flex items-center justify-between gap-3 shrink-0 bg-card">
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      setMode("view");
                      setMobileShowDetail(false);
                    }}
                    className="md:hidden text-muted-foreground hover:text-foreground"
                    aria-label="Back to list"
                  >
                    <ArrowLeft className="size-4" strokeWidth={1.5} />
                  </button>
                  <span className="text-body-strong">
                    {mode === "create" ? "New Knowledge Base tip" : "Edit KB article"}
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setMode("view");
                      if (!selectedArticle) setMobileShowDetail(false);
                    }}
                  >
                    Cancel
                  </Button>
                  <Button
                    type="submit"
                    variant="primary"
                    size="sm"
                    disabled={!formTitle.trim() || saving}
                  >
                    {saving ? "Saving..." : "Save article"}
                  </Button>
                </div>
              </div>

              <div className="flex-1 overflow-y-auto px-5 py-5">
                <div className="max-w-[760px] space-y-4">
                  {error && (
                    <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-[13px] text-destructive">
                      {error}
                    </div>
                  )}

                  <div className="space-y-1">
                    <label className="block text-meta">Title</label>
                    <input
                      type="text"
                      required
                      value={formTitle}
                      onChange={(e) => setFormTitle(e.target.value)}
                      placeholder="e.g. Fix Print Spooler stuck on Deleting..."
                      className={inputBaseClass}
                    />
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div className="space-y-1">
                      <label className="block text-meta">Category</label>
                      <select
                        value={formCategoryId}
                        onChange={(e) => setFormCategoryId(e.target.value)}
                        className={cn(selectBaseClass, "w-full h-9")}
                      >
                        <option value="">General / Uncategorized</option>
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
                          onClick={() => setFormVisibility("INTERNAL")}
                          className={cn(
                            "rounded-sm text-[13px] font-medium inline-flex items-center justify-center gap-1.5 transition-colors duration-75",
                            formVisibility === "INTERNAL"
                              ? "bg-card text-foreground border border-border"
                              : "text-muted-foreground hover:text-foreground"
                          )}
                        >
                          <Lock className="size-3.5" strokeWidth={1.5} />
                          <span>IT Runbook</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => setFormVisibility("PUBLIC")}
                          className={cn(
                            "rounded-sm text-[13px] font-medium inline-flex items-center justify-center gap-1.5 transition-colors duration-75",
                            formVisibility === "PUBLIC"
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
                    <label className="block text-meta">
                      Symptoms / Error description
                    </label>
                    <textarea
                      rows={2}
                      value={formSymptoms}
                      onChange={(e) => setFormSymptoms(e.target.value)}
                      placeholder="Biểu hiện lỗi, thông báo popup hoặc hiện tượng người dùng hay gặp..."
                      className={inputBaseClass}
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="block text-meta">Root cause (optional)</label>
                    <textarea
                      rows={2}
                      value={formRootCause}
                      onChange={(e) => setFormRootCause(e.target.value)}
                      placeholder="Nguyên nhân gốc rễ gây ra lỗi..."
                      className={inputBaseClass}
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="block text-meta">
                      Resolution steps (one step per line)
                    </label>
                    <textarea
                      rows={5}
                      value={formStepsText}
                      onChange={(e) => setFormStepsText(e.target.value)}
                      placeholder={"Bước 1: Kiểm tra...\nBước 2: Mở...\nBước 3: Khởi động lại..."}
                      className={inputBaseClass}
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="block text-meta">
                      Commands / Technical notes (PowerShell, CMD, Registry, Config...)
                    </label>
                    <textarea
                      rows={3}
                      value={formNotes}
                      onChange={(e) => setFormNotes(e.target.value)}
                      placeholder="net stop spooler&#10;net start spooler"
                      className={cn(inputBaseClass, "font-mono text-[13px]")}
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="block text-meta">
                      Keywords (comma-separated for instant search &amp; Portal matching)
                    </label>
                    <input
                      type="text"
                      value={formKeywords}
                      onChange={(e) => setFormKeywords(e.target.value)}
                      placeholder="vpn, forticlient, spooler, error 0x800..."
                      className={inputBaseClass}
                    />
                  </div>

                  <div className="space-y-1.5">
                    <label className="block text-meta">
                      Screenshots &amp; attachments (Ctrl+V to paste directly)
                    </label>
                    <PasteImageUploader
                      ref={uploaderRef}
                      kbArticleId={mode === "edit" ? selectedArticle?.id : undefined}
                      attachments={formAttachments}
                      onChange={setFormAttachments}
                    />
                  </div>
                </div>
              </div>
            </form>
          ) : selectedArticle ? (
            <>
              <div className="h-11 px-4 border-b border-border flex items-center justify-between gap-3 shrink-0 bg-card">
                <div className="flex items-center gap-2 min-w-0">
                  <button
                    type="button"
                    onClick={() => setMobileShowDetail(false)}
                    className="md:hidden text-muted-foreground hover:text-foreground shrink-0"
                    aria-label="Back to list"
                  >
                    <ArrowLeft className="size-4" strokeWidth={1.5} />
                  </button>
                  <VisibilityBadge visibility={selectedArticle.visibility} />
                  {selectedArticle.category && (
                    <TopicBadge
                      label={selectedArticle.category.name}
                      iconSlug={selectedArticle.category.slug}
                    />
                  )}
                  {selectedArticle.source_ticket && (
                    <Link
                      href={`/workspace/tickets/${selectedArticle.source_ticket.id}`}
                      onClick={() =>
                        startNavigation(
                          `/workspace/tickets/${selectedArticle.source_ticket!.id}`
                        )
                      }
                      className="inline-flex h-6 items-center gap-1 rounded-sm border border-border bg-muted/60 px-2 text-[12px] font-mono text-foreground hover:bg-muted shrink-0"
                      title={selectedArticle.source_ticket.title}
                    >
                      <span>{selectedArticle.source_ticket.ticket_code}</span>
                      <ExternalLink className="size-3 text-muted-foreground" strokeWidth={1.5} />
                    </Link>
                  )}
                </div>

                <div className="flex items-center gap-1.5 shrink-0">
                  {selectedArticle.steps.length > 0 && (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() =>
                        void handleCopy(
                          "steps",
                          selectedArticle.steps
                            .map((s, idx) => `${idx + 1}. ${s}`)
                            .join("\n")
                        )
                      }
                    >
                      {copiedKey === "steps" ? (
                        <Check className="size-3.5" strokeWidth={1.5} />
                      ) : (
                        <Copy className="size-3.5" strokeWidth={1.5} />
                      )}
                      <span className="hidden sm:inline">
                        {copiedKey === "steps" ? "Copied" : "Copy steps"}
                      </span>
                    </Button>
                  )}
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => openEditMode(selectedArticle)}
                  >
                    <Edit3 className="size-3.5" strokeWidth={1.5} />
                    <span>Edit</span>
                  </Button>

                  {confirmDelete ? (
                    <div className="flex items-center gap-1">
                      <Button
                        type="button"
                        variant="destructive"
                        size="sm"
                        disabled={saving}
                        onClick={() => void handleDelete()}
                      >
                        Confirm
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => setConfirmDelete(false)}
                      >
                        Cancel
                      </Button>
                    </div>
                  ) : (
                    <Button
                      type="button"
                      variant="icon"
                      onClick={() => setConfirmDelete(true)}
                      title="Delete article"
                    >
                      <Trash2 className="size-3.5" strokeWidth={1.5} />
                    </Button>
                  )}
                </div>
              </div>

              <div className="flex-1 overflow-y-auto px-5 py-5">
                <div className="max-w-[760px] space-y-5">
                  <div>
                    <h1 className="text-[18px] leading-[24px] font-medium text-foreground">
                      {selectedArticle.title}
                    </h1>
                    <p className="mt-1 text-meta">
                      {selectedArticle.author
                        ? `By ${selectedArticle.author.full_name}`
                        : "Seeded guide"}
                      {" · "}Updated {formatDateTime(selectedArticle.updated_at)}
                      {selectedArticle.updated_by &&
                        selectedArticle.updated_by.id !== selectedArticle.author?.id &&
                        ` by ${selectedArticle.updated_by.full_name}`}
                    </p>

                    {selectedArticle.keywords.length > 0 && (
                      <div className="mt-2.5 flex flex-wrap gap-1.5">
                        {selectedArticle.keywords.map((kw) => (
                          <span
                            key={kw}
                            className="inline-flex h-5 items-center rounded-xs border border-border bg-background px-1.5 text-[12px] text-muted-foreground"
                          >
                            #{kw}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>

                  {selectedArticle.symptoms && (
                    <div className="rounded-md border border-border bg-background p-3.5 space-y-1">
                      <p className="text-[12px] font-medium uppercase tracking-wide text-muted-foreground">
                        Symptoms
                      </p>
                      <p className="text-body whitespace-pre-wrap">
                        {selectedArticle.symptoms}
                      </p>
                    </div>
                  )}

                  {selectedArticle.root_cause && (
                    <div className="space-y-1">
                      <p className="text-[12px] font-medium uppercase tracking-wide text-muted-foreground">
                        Root cause
                      </p>
                      <p className="text-body whitespace-pre-wrap">
                        {selectedArticle.root_cause}
                      </p>
                    </div>
                  )}

                  {selectedArticle.steps.length > 0 && (
                    <div className="space-y-2">
                      <p className="text-[12px] font-medium uppercase tracking-wide text-muted-foreground">
                        Resolution steps
                      </p>
                      <ol className="space-y-2">
                        {selectedArticle.steps.map((step, idx) => (
                          <li key={idx} className="flex items-start gap-2.5 text-body">
                            <span className="size-5 rounded-xs bg-muted text-foreground text-[12px] font-medium inline-flex items-center justify-center shrink-0 mt-0.5 tabular-nums">
                              {idx + 1}
                            </span>
                            <span className="whitespace-pre-wrap">{step}</span>
                          </li>
                        ))}
                      </ol>
                    </div>
                  )}

                  {selectedArticle.notes && (
                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between">
                        <p className="text-[12px] font-medium uppercase tracking-wide text-muted-foreground">
                          Commands &amp; technical notes
                        </p>
                        <button
                          type="button"
                          onClick={() =>
                            void handleCopy("notes", selectedArticle.notes || "")
                          }
                          className="inline-flex items-center gap-1 text-[12px] text-muted-foreground hover:text-foreground"
                        >
                          {copiedKey === "notes" ? (
                            <Check className="size-3" strokeWidth={1.5} />
                          ) : (
                            <Copy className="size-3" strokeWidth={1.5} />
                          )}
                          <span>{copiedKey === "notes" ? "Copied" : "Copy"}</span>
                        </button>
                      </div>
                      <pre className="rounded-md border border-border bg-background px-3.5 py-2.5 font-mono text-[13px] leading-5 text-foreground overflow-x-auto whitespace-pre-wrap">
                        {selectedArticle.notes}
                      </pre>
                    </div>
                  )}

                  {selectedArticle.attachments.length > 0 && (
                    <div className="space-y-2">
                      <p className="text-[12px] font-medium uppercase tracking-wide text-muted-foreground">
                        Screenshots &amp; attachments ({selectedArticle.attachments.length})
                      </p>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        {selectedArticle.attachments.map((att) => {
                          const url = buildAttachmentUrl(att.download_url);
                          const isImage = att.content_type.startsWith("image/");
                          if (isImage) {
                            return (
                              <button
                                key={att.id}
                                type="button"
                                onClick={() =>
                                  setLightboxUrl({ url, name: att.file_name })
                                }
                                className="group text-left rounded-md border border-border bg-background overflow-hidden hover:border-foreground/40 transition-colors duration-75"
                              >
                                <img
                                  src={url}
                                  alt={att.file_name}
                                  className="w-full h-44 object-cover bg-muted"
                                />
                                <div className="px-3 py-1.5 border-t border-border-subtle flex items-center justify-between text-[12px] text-muted-foreground">
                                  <span className="truncate">{att.file_name}</span>
                                  <span className="shrink-0 ml-2">Click to zoom</span>
                                </div>
                              </button>
                            );
                          }
                          return (
                            <a
                              key={att.id}
                              href={url}
                              target="_blank"
                              rel="noreferrer"
                              className="flex items-center gap-2.5 rounded-md border border-border bg-background px-3 py-2.5 hover:bg-muted/60"
                            >
                              <FileText
                                className="size-4 text-muted-foreground shrink-0"
                                strokeWidth={1.5}
                              />
                              <span className="text-[13px] text-foreground truncate">
                                {att.file_name}
                              </span>
                            </a>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center px-6 text-center gap-2">
              <BookOpen className="size-6 text-faint" strokeWidth={1.5} />
              <p className="text-body">
                Select a troubleshooting guide on the left, or save a new tip.
              </p>
              <Button type="button" variant="outline" size="sm" onClick={openCreateMode}>
                <Plus className="size-3.5" strokeWidth={1.5} />
                <span>New tip</span>
              </Button>
            </div>
          )}
        </section>
      </div>

      {/* Image Lightbox */}
      {lightboxUrl && (
        <div
          role="dialog"
          aria-modal="true"
          onClick={() => setLightboxUrl(null)}
          className="anim-scrim fixed inset-0 z-50 bg-[var(--scrim)] backdrop-blur-[2px] flex items-center justify-center p-4"
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="anim-popover relative max-w-4xl max-h-[88dvh] rounded-lg border border-border bg-card shadow-popover overflow-hidden flex flex-col"
          >
            <div className="h-10 px-4 border-b border-border flex items-center justify-between gap-4">
              <span className="text-meta truncate">{lightboxUrl.name}</span>
              <Button
                type="button"
                variant="icon"
                onClick={() => setLightboxUrl(null)}
                aria-label="Close image preview"
              >
                <X className="size-4" strokeWidth={1.5} />
              </Button>
            </div>
            <div className="p-3 overflow-auto bg-background flex items-center justify-center">
              <img
                src={lightboxUrl.url}
                alt={lightboxUrl.name}
                className="max-h-[76dvh] w-auto object-contain rounded-sm"
              />
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}

export default function KnowledgeBasePage() {
  return (
    <Suspense fallback={null}>
      <KnowledgeBaseContent />
    </Suspense>
  );
}
