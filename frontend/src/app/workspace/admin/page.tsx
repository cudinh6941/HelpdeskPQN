"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, BookOpen, Play, RefreshCw } from "lucide-react";

import { AppShell } from "@/components/AppShell";
import {
  Button,
  Checkbox,
  SkeletonRow,
  TopicBadge,
  inputBaseClass,
  selectBaseClass,
} from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import {
  formatRelativeTime,
  PRIORITY_LABELS,
  ROLE_LABELS,
} from "@/lib/formatters";
import {
  AutomationSettings,
  Category,
  KbArticleDetail,
  OutboxEvent,
  SlaPolicy,
  SupportGroup,
  TicketPriority,
  User,
  UserRole,
} from "@/lib/types";

export default function AdminPage() {
  const { user } = useAuth();
  const [categories, setCategories] = useState<Category[]>([]);
  const [groups, setGroups] = useState<SupportGroup[]>([]);
  const [slas, setSlas] = useState<SlaPolicy[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [outbox, setOutbox] = useState<OutboxEvent[]>([]);
  const [autoSettings, setAutoSettings] = useState<AutomationSettings>({
    auto_assign_enabled: true,
    auto_close_resolved_hours: 48,
  });
  const [loading, setLoading] = useState(true);

  const [newCatName, setNewCatName] = useState("");
  const [newCatSlug, setNewCatSlug] = useState("");
  const [newCatPriority, setNewCatPriority] = useState<TicketPriority>("MEDIUM");
  const [kbArticles, setKbArticles] = useState<KbArticleDetail[]>([]);

  const [autoBusy, setAutoBusy] = useState(false);
  const [autoStatusMsg, setAutoStatusMsg] = useState<string | null>(null);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [cats, grps, policies, usr, events, autoCfg, kbRes] = await Promise.all([
        api.adminListCategories(),
        api.adminListGroups(),
        api.adminListSlaPolicies(),
        api.adminListUsers(),
        api.adminListOutboxEvents(),
        api.adminGetAutomationSettings(),
        api.listKbArticles().catch(() => ({ items: [], total: 0 })),
      ]);
      setCategories(cats);
      setGroups(grps);
      setSlas(policies);
      setUsers(usr);
      setOutbox(events);
      setAutoSettings(autoCfg);
      setKbArticles(kbRes.items);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  const handleCreateCategory = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newCatName.trim() || !newCatSlug.trim()) return;
    await api.adminCreateCategory({
      name: newCatName.trim(),
      slug: newCatSlug.trim().toLowerCase(),
      default_group_id: groups[0]?.id || null,
      default_priority: newCatPriority,
    });
    setNewCatName("");
    setNewCatSlug("");
    await loadAll();
  };

  const handleToggleAutoAssign = async (next: boolean) => {
    setAutoBusy(true);
    setAutoStatusMsg(null);
    try {
      const updated = await api.adminUpdateAutomationSettings({
        auto_assign_enabled: next,
      });
      setAutoSettings(updated);
    } finally {
      setAutoBusy(false);
    }
  };

  const handleSaveAutoCloseHours = async (e: React.FormEvent) => {
    e.preventDefault();
    setAutoBusy(true);
    setAutoStatusMsg(null);
    try {
      const updated = await api.adminUpdateAutomationSettings({
        auto_close_resolved_hours: autoSettings.auto_close_resolved_hours,
      });
      setAutoSettings(updated);
      setAutoStatusMsg(`Saved auto-close threshold: ${updated.auto_close_resolved_hours}h`);
    } finally {
      setAutoBusy(false);
    }
  };

  const handleRunAutoClose = async () => {
    setAutoBusy(true);
    setAutoStatusMsg(null);
    try {
      const res = await api.adminRunAutoCloseNow(autoSettings.auto_close_resolved_hours);
      setAutoStatusMsg(`Auto-closed ${res.auto_closed} resolved ticket(s).`);
      await loadAll();
    } finally {
      setAutoBusy(false);
    }
  };

  const handleRetryOutbox = async (eventId: string) => {
    await api.adminRetryOutboxEvent(eventId);
    await loadAll();
  };

  const handleRoleChange = async (userId: string, role: UserRole) => {
    await api.adminUpdateUserRole(userId, role);
    await loadAll();
  };

  const internalKbCount = kbArticles.filter((a) => a.visibility === "INTERNAL").length;
  const publicKbCount = kbArticles.filter((a) => a.visibility === "PUBLIC").length;

  return (
    <AppShell>
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-[17px] leading-[22px] font-medium text-foreground">
              System Settings, Automation &amp; Outbox Log
            </h1>
            <p className="text-meta">
              Auto-assign, auto-close, Knowledge Base guides, SLA policies, LDAP users, and n8n Outbox
            </p>
          </div>
          <Button variant="outline" onClick={() => void loadAll()}>
            <RefreshCw className="size-3.5" strokeWidth={1.5} />
            <span>Refresh</span>
          </Button>
        </div>

        {loading ? (
          <div className="rounded-lg border border-border bg-card overflow-hidden">
            <SkeletonRow count={4} compact />
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
            {/* Left column */}
            <div className="lg:col-span-6 space-y-4">
              {/* Automation Settings */}
              <div className="rounded-lg border border-border bg-card overflow-hidden">
                <div className="h-10 px-4 border-b border-border bg-background flex items-center justify-between">
                  <span className="text-body-strong">Automation (Auto-Assign &amp; Auto-Close)</span>
                </div>

                <div className="p-4 space-y-3">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-body-strong">Auto-assign new tickets</p>
                      <p className="text-meta">
                        Route new tickets to the least-loaded IT agent in the support group
                      </p>
                    </div>
                    <Checkbox
                      checked={autoSettings.auto_assign_enabled}
                      onChange={(next) => void handleToggleAutoAssign(next)}
                      ariaLabel="Toggle auto-assign new tickets"
                    />
                  </div>

                  <form
                    onSubmit={handleSaveAutoCloseHours}
                    className="pt-3 border-t border-border-subtle flex flex-wrap items-center justify-between gap-2"
                  >
                    <div>
                      <p className="text-body-strong">Auto-close resolved tickets</p>
                      <p className="text-meta">
                        Close RESOLVED tickets with no user response after hours
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <input
                        type="number"
                        min={1}
                        max={720}
                        value={autoSettings.auto_close_resolved_hours}
                        onChange={(e) =>
                          setAutoSettings((prev) => ({
                            ...prev,
                            auto_close_resolved_hours: Number(e.target.value) || 48,
                          }))
                        }
                        className="w-20 h-8 rounded-md border border-input bg-card px-2.5 text-[13px] tabular-nums"
                      />
                      <Button type="submit" variant="outline" size="sm" disabled={autoBusy}>
                        Save
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        disabled={autoBusy}
                        onClick={() => void handleRunAutoClose()}
                      >
                        <Play className="size-3" strokeWidth={1.5} />
                        <span>Run now</span>
                      </Button>
                    </div>
                  </form>

                  {autoStatusMsg && (
                    <p className="text-meta text-foreground">{autoStatusMsg}</p>
                  )}
                </div>
              </div>

              {/* Knowledge Base Summary Card */}
              <div className="rounded-lg border border-border bg-card overflow-hidden">
                <div className="h-10 px-4 border-b border-border bg-background flex items-center justify-between">
                  <span className="inline-flex items-center gap-1.5 text-body-strong">
                    <BookOpen className="size-4 text-muted-foreground" strokeWidth={1.5} />
                    <span>Knowledge Base &amp; IT Runbooks</span>
                  </span>
                  <span className="text-meta tabular-nums">{kbArticles.length}</span>
                </div>

                <div className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className="space-y-1">
                    <p className="text-body">
                      {internalKbCount} internal IT runbooks · {publicKbCount} Portal self-help guides
                    </p>
                    <p className="text-meta">
                      Dedicated DB table with screenshots, symptoms, root cause, and ticket links.
                    </p>
                  </div>
                  <Link
                    href="/workspace/kb"
                    className="inline-flex h-8 items-center gap-1.5 rounded-sm bg-primary px-3 text-[13px] font-medium text-primary-foreground hover:opacity-90 shrink-0"
                  >
                    <span>Open Knowledge Base</span>
                    <ArrowRight className="size-3.5" strokeWidth={1.5} />
                  </Link>
                </div>
              </div>

              {/* Categories */}
              <div className="rounded-lg border border-border bg-card overflow-hidden">
                <div className="h-10 px-4 border-b border-border bg-background flex items-center justify-between">
                  <span className="text-body-strong">Categories</span>
                  <span className="text-meta tabular-nums">{categories.length}</span>
                </div>

                <div className="divide-y divide-border-subtle">
                  {categories.map((c) => (
                    <div
                      key={c.id}
                      className="px-4 py-2.5 flex items-center justify-between gap-3"
                    >
                      <div className="min-w-0">
                        <p className="text-body-strong truncate">{c.name}</p>
                        <p className="text-meta-faint font-mono truncate">{c.slug}</p>
                      </div>
                      <TopicBadge
                        label={PRIORITY_LABELS[c.default_priority]}
                        iconSlug={c.slug}
                      />
                    </div>
                  ))}
                </div>

                <form
                  onSubmit={handleCreateCategory}
                  className="p-3 border-t border-border bg-background grid grid-cols-1 sm:grid-cols-[1fr_1fr_auto] gap-2"
                >
                  <input
                    type="text"
                    required
                    value={newCatName}
                    onChange={(e) => setNewCatName(e.target.value)}
                    placeholder="Category name"
                    className={inputBaseClass}
                  />
                  <input
                    type="text"
                    required
                    value={newCatSlug}
                    onChange={(e) => setNewCatSlug(e.target.value)}
                    placeholder="slug-name"
                    className={`${inputBaseClass} font-mono`}
                  />
                  <div className="flex gap-2">
                    <select
                      value={newCatPriority}
                      onChange={(e) => setNewCatPriority(e.target.value as TicketPriority)}
                      className={selectBaseClass}
                    >
                      <option value="LOW">Low</option>
                      <option value="MEDIUM">Medium</option>
                      <option value="HIGH">High</option>
                      <option value="CRITICAL">Urgent</option>
                    </select>
                    <Button type="submit" variant="primary">
                      Add
                    </Button>
                  </div>
                </form>
              </div>
            </div>

            {/* Right column */}
            <div className="lg:col-span-6 space-y-4">
              {/* SLA Policies */}
              <div className="rounded-lg border border-border bg-card overflow-hidden">
                <div className="h-10 px-4 border-b border-border bg-background flex items-center justify-between">
                  <span className="text-body-strong">SLA Policies</span>
                  <span className="text-meta tabular-nums">{slas.length}</span>
                </div>
                <div className="divide-y divide-border-subtle">
                  {slas.map((s) => (
                    <div
                      key={s.id}
                      className="px-4 py-2.5 flex items-center justify-between gap-3"
                    >
                      <div>
                        <p className="text-body-strong">{s.name}</p>
                        <p className="text-meta">
                          {s.business_hours_only ? "Business hours" : "24/7"} / Warn at{" "}
                          {s.warning_threshold_pct}%
                        </p>
                      </div>
                      <div className="text-right text-meta tabular-nums">
                        <p>Response: {s.first_response_minutes}m</p>
                        <p>Resolve: {s.resolution_minutes}m</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Users */}
              <div className="rounded-lg border border-border bg-card overflow-hidden">
                <div className="h-10 px-4 border-b border-border bg-background flex items-center justify-between">
                  <span className="text-body-strong">Users (LDAP / AD)</span>
                  <span className="text-meta tabular-nums">{users.length}</span>
                </div>
                <div className="divide-y divide-border-subtle">
                  {users.map((u) => (
                    <div
                      key={u.id}
                      className="px-4 py-2.5 flex items-center justify-between gap-3"
                    >
                      <div className="min-w-0">
                        <p className="text-body-strong truncate">
                          {u.full_name}{" "}
                          <span className="text-meta font-mono">({u.username})</span>
                        </p>
                        <p className="text-meta-faint truncate">{u.email}</p>
                      </div>
                      {user?.role === "SYS_ADMIN" ? (
                        <select
                          value={u.role}
                          onChange={(e) =>
                            void handleRoleChange(u.id, e.target.value as UserRole)
                          }
                          className={selectBaseClass}
                        >
                          <option value="END_USER">End user</option>
                          <option value="IT_AGENT">IT Agent</option>
                          <option value="IT_LEAD">IT Lead</option>
                          <option value="SYS_ADMIN">Sys Admin</option>
                        </select>
                      ) : (
                        <span className="text-meta">{ROLE_LABELS[u.role]}</span>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* Outbox Events */}
              <div className="rounded-lg border border-border bg-card overflow-hidden">
                <div className="h-10 px-4 border-b border-border bg-background flex items-center justify-between">
                  <span className="text-body-strong">Transactional Outbox (n8n)</span>
                  <span className="text-meta tabular-nums">{outbox.length}</span>
                </div>
                <div className="max-h-[380px] overflow-y-auto divide-y divide-border-subtle">
                  {outbox.map((ev) => (
                    <div
                      key={ev.id}
                      className="px-4 py-2.5 flex items-start justify-between gap-3"
                    >
                      <div className="min-w-0 space-y-0.5">
                        <div className="flex items-center gap-2">
                          <span className="text-[13px] font-mono font-medium text-foreground">
                            {ev.event_type}
                          </span>
                          <span
                            className={`inline-flex h-5 items-center rounded-sm px-1.5 text-[12px] font-medium ${
                              ev.status === "SENT"
                                ? "bg-sla-neutral text-sla-neutral-fg"
                                : ev.status === "FAILED"
                                ? "bg-sla-breached text-sla-breached-fg"
                                : "bg-sla-urgent text-sla-urgent-fg"
                            }`}
                          >
                            {ev.status}
                          </span>
                        </div>
                        <p className="text-meta truncate">
                          {ev.payload?.summary || ev.aggregate_id}
                        </p>
                        <p className="text-meta-faint tabular-nums">
                          {formatRelativeTime(ev.created_at)} / Retries: {ev.retry_count}
                        </p>
                        {ev.last_error && (
                          <p className="text-[12px] text-destructive truncate">
                            {ev.last_error}
                          </p>
                        )}
                      </div>

                      {ev.status === "FAILED" && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => void handleRetryOutbox(ev.id)}
                        >
                          Retry
                        </Button>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
