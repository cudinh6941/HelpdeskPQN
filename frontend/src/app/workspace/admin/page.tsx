"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowRight, BookOpen, Play, Plus, RefreshCw, Search, X } from "lucide-react";

import { AppShell } from "@/components/AppShell";
import {
  Button,
  Checkbox,
  SkeletonRow,
  inputBaseClass,
  selectBaseClass,
} from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { cn } from "@/lib/cn";
import {
  formatRelativeTime,
  isItRole,
  ROLE_LABELS,
} from "@/lib/formatters";
import {
  AutomationSettings,
  BusinessCalendar,
  CannedResponse,
  Category,
  Department,
  KbArticleDetail,
  OutboxEvent,
  SlaPolicy,
  SupportGroupDetail,
  TicketPriority,
  TicketStatus,
  User,
  UserRole,
} from "@/lib/types";

type AdminTab = "general" | "groups" | "users" | "macros" | "outbox";

const WEEKDAYS: Array<{ key: string; label: string }> = [
  { key: "0", label: "Mon" },
  { key: "1", label: "Tue" },
  { key: "2", label: "Wed" },
  { key: "3", label: "Thu" },
  { key: "4", label: "Fri" },
  { key: "5", label: "Sat" },
  { key: "6", label: "Sun" },
];

export default function AdminPage() {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState<AdminTab>("general");
  const [categories, setCategories] = useState<Category[]>([]);
  const [groups, setGroups] = useState<SupportGroupDetail[]>([]);
  const [slas, setSlas] = useState<SlaPolicy[]>([]);
  const [calendar, setCalendar] = useState<BusinessCalendar | null>(null);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [outbox, setOutbox] = useState<OutboxEvent[]>([]);
  const [autoSettings, setAutoSettings] = useState<AutomationSettings>({
    auto_assign_enabled: true,
    auto_close_resolved_hours: 48,
  });
  const [kbArticles, setKbArticles] = useState<KbArticleDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState<{ type: "ok" | "err"; text: string } | null>(null);

  // Automation
  const [autoBusy, setAutoBusy] = useState(false);

  // SLA Drafts
  const [slaDrafts, setSlaDrafts] = useState<
    Record<
      string,
      {
        first_response_minutes: number;
        resolution_minutes: number;
        warning_threshold_pct: number;
        business_hours_only: boolean;
      }
    >
  >({});

  // Business Calendar draft
  const [calName, setCalName] = useState("");
  const [calTz, setCalTz] = useState("Asia/Ho_Chi_Minh");
  const [calWorkDays, setCalWorkDays] = useState<Record<string, [string, string]>>({});
  const [calHolidays, setCalHolidays] = useState<string[]>([]);
  const [newHolidayDate, setNewHolidayDate] = useState("");

  // Groups & Members
  const [newGroupCode, setNewGroupCode] = useState("");
  const [newGroupName, setNewGroupName] = useState("");
  const [newGroupDesc, setNewGroupDesc] = useState("");
  const [memberDrafts, setMemberDrafts] = useState<
    Record<string, { user_id: string; is_lead: boolean }>
  >({});

  // Categories
  const [newCatName, setNewCatName] = useState("");
  const [newCatSlug, setNewCatSlug] = useState("");
  const [newCatGroupId, setNewCatGroupId] = useState("");
  const [newCatPriority, setNewCatPriority] = useState<TicketPriority>("MEDIUM");

  // Departments
  const [newDeptCode, setNewDeptCode] = useState("");
  const [newDeptName, setNewDeptName] = useState("");

  // Users
  const [userSearch, setUserSearch] = useState("");
  const [newUserUsername, setNewUserUsername] = useState("");
  const [newUserFullName, setNewUserFullName] = useState("");
  const [newUserEmail, setNewUserEmail] = useState("");
  const [newUserPassword, setNewUserPassword] = useState("Password123!");
  const [newUserRole, setNewUserRole] = useState<UserRole>("END_USER");
  const [newUserDeptId, setNewUserDeptId] = useState("");
  const [userChannelDrafts, setUserChannelDrafts] = useState<
    Record<string, { telegram_chat_id: string; zalo_user_id: string }>
  >({});

  // Outbox
  const [outboxFilter, setOutboxFilter] = useState<"ALL" | "PENDING" | "SENT" | "FAILED">("ALL");

  // Macros (Canned Responses)
  const [macros, setMacros] = useState<CannedResponse[]>([]);
  const [newMacroShortcut, setNewMacroShortcut] = useState("");
  const [newMacroTitle, setNewMacroTitle] = useState("");
  const [newMacroBody, setNewMacroBody] = useState("");
  const [newMacroStatus, setNewMacroStatus] = useState<TicketStatus | "">("");
  const [newMacroInternal, setNewMacroInternal] = useState(false);

  const showError = (err: unknown, fallback: string) => {
    setNotice({
      type: "err",
      text: err instanceof Error ? err.message : fallback,
    });
  };

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [cats, grps, policies, cal, depts, usr, events, autoCfg, kbRes, macroList] =
        await Promise.all([
          api.adminListCategories(),
          api.adminListGroups(),
          api.adminListSlaPolicies(),
          api.adminGetBusinessCalendar(),
          api.adminListDepartments(),
          api.adminListUsers(),
          api.adminListOutboxEvents(),
          api.adminGetAutomationSettings(),
          api.listKbArticles().catch(() => ({ items: [], total: 0 })),
          api.listMacros().catch(() => [] as CannedResponse[]),
        ]);
      setCategories(cats);
      setGroups(grps);
      setSlas(policies);
      setCalendar(cal);
      setDepartments(depts);
      setUsers(usr);
      setOutbox(events);
      setAutoSettings(autoCfg);
      setKbArticles(kbRes.items);
      setMacros(macroList);

      if (grps.length > 0 && !newCatGroupId) {
        setNewCatGroupId(grps[0].id);
      }

      const nextSlaDrafts: typeof slaDrafts = {};
      for (const s of policies) {
        nextSlaDrafts[s.id] = {
          first_response_minutes: s.first_response_minutes,
          resolution_minutes: s.resolution_minutes,
          warning_threshold_pct: s.warning_threshold_pct,
          business_hours_only: s.business_hours_only,
        };
      }
      setSlaDrafts(nextSlaDrafts);

      setCalName(cal.name);
      setCalTz(cal.timezone);
      setCalWorkDays(cal.work_days || {});
      setCalHolidays(cal.holidays || []);

      const nextChannelDrafts: typeof userChannelDrafts = {};
      for (const u of usr) {
        nextChannelDrafts[u.id] = {
          telegram_chat_id: u.telegram_chat_id || "",
          zalo_user_id: u.zalo_user_id || "",
        };
      }
      setUserChannelDrafts(nextChannelDrafts);
    } catch (err: unknown) {
      showError(err, "Failed to load admin configuration.");
    } finally {
      setLoading(false);
    }
  }, [newCatGroupId]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  const activeItUsers = useMemo(
    () => users.filter((u) => u.is_active && isItRole(u.role)),
    [users]
  );

  const filteredUsers = useMemo(() => {
    const q = userSearch.trim().toLowerCase();
    if (!q) return users;
    return users.filter(
      (u) =>
        u.full_name.toLowerCase().includes(q) ||
        u.username.toLowerCase().includes(q) ||
        u.email.toLowerCase().includes(q)
    );
  }, [users, userSearch]);

  const filteredOutbox = useMemo(() => {
    if (outboxFilter === "ALL") return outbox;
    return outbox.filter((ev) => ev.status === outboxFilter);
  }, [outbox, outboxFilter]);

  /* ===== Automation ===== */
  const handleToggleAutoAssign = async (next: boolean) => {
    setAutoBusy(true);
    setNotice(null);
    try {
      const updated = await api.adminUpdateAutomationSettings({ auto_assign_enabled: next });
      setAutoSettings(updated);
      setNotice({
        type: "ok",
        text: `Auto-assign ${updated.auto_assign_enabled ? "enabled" : "disabled"}.`,
      });
    } catch (err: unknown) {
      showError(err, "Could not update auto-assign.");
    } finally {
      setAutoBusy(false);
    }
  };

  const handleSaveAutoCloseHours = async (e: React.FormEvent) => {
    e.preventDefault();
    setAutoBusy(true);
    setNotice(null);
    try {
      const updated = await api.adminUpdateAutomationSettings({
        auto_close_resolved_hours: autoSettings.auto_close_resolved_hours,
      });
      setAutoSettings(updated);
      setNotice({
        type: "ok",
        text: `Saved auto-close threshold: ${updated.auto_close_resolved_hours}h.`,
      });
    } catch (err: unknown) {
      showError(err, "Could not update auto-close threshold.");
    } finally {
      setAutoBusy(false);
    }
  };

  const handleRunAutoClose = async () => {
    setAutoBusy(true);
    setNotice(null);
    try {
      const res = await api.adminRunAutoCloseNow(autoSettings.auto_close_resolved_hours);
      setNotice({ type: "ok", text: `Auto-closed ${res.auto_closed} resolved ticket(s).` });
      await loadAll();
    } catch (err: unknown) {
      showError(err, "Could not run auto-close.");
    } finally {
      setAutoBusy(false);
    }
  };

  /* ===== SLA Policies & Business Calendar ===== */
  const handleSaveSlaPolicy = async (policyId: string) => {
    const draft = slaDrafts[policyId];
    if (!draft) return;
    setNotice(null);
    try {
      await api.adminUpdateSlaPolicy(policyId, draft);
      setNotice({ type: "ok", text: "Saved SLA policy." });
      await loadAll();
    } catch (err: unknown) {
      showError(err, "Failed to update SLA policy.");
    }
  };

  const handleToggleWorkDay = (dayKey: string, enabled: boolean) => {
    setCalWorkDays((prev) => {
      const next = { ...prev };
      if (enabled) {
        next[dayKey] = next[dayKey] || ["08:00", "17:30"];
      } else {
        delete next[dayKey];
      }
      return next;
    });
  };

  const handleWorkDayTime = (dayKey: string, index: 0 | 1, value: string) => {
    setCalWorkDays((prev) => {
      const current = prev[dayKey] || ["08:00", "17:30"];
      const updated: [string, string] = [
        index === 0 ? value : current[0],
        index === 1 ? value : current[1],
      ];
      return { ...prev, [dayKey]: updated };
    });
  };

  const handleAddHoliday = () => {
    if (!newHolidayDate) return;
    setCalHolidays((prev) =>
      prev.includes(newHolidayDate) ? prev : [...prev, newHolidayDate].sort()
    );
    setNewHolidayDate("");
  };

  const handleSaveCalendar = async (e: React.FormEvent) => {
    e.preventDefault();
    setNotice(null);
    try {
      const updated = await api.adminUpdateBusinessCalendar({
        name: calName,
        timezone: calTz,
        work_days: calWorkDays,
        holidays: calHolidays,
      });
      setCalendar(updated);
      setNotice({ type: "ok", text: "Saved Business Calendar." });
    } catch (err: unknown) {
      showError(err, "Failed to save Business Calendar.");
    }
  };

  /* ===== Groups & Categories ===== */
  const handleCreateGroup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newGroupCode.trim() || !newGroupName.trim()) return;
    setNotice(null);
    try {
      await api.adminCreateGroup({
        code: newGroupCode.trim().toUpperCase(),
        name: newGroupName.trim(),
        description: newGroupDesc.trim() || undefined,
      });
      setNewGroupCode("");
      setNewGroupName("");
      setNewGroupDesc("");
      setNotice({ type: "ok", text: "Created support group." });
      await loadAll();
    } catch (err: unknown) {
      showError(err, "Failed to create group.");
    }
  };

  const handleAddMember = async (groupId: string) => {
    const draft = memberDrafts[groupId];
    const targetUserId = draft?.user_id || activeItUsers[0]?.id;
    if (!targetUserId) return;
    setNotice(null);
    try {
      await api.adminAddGroupMember(groupId, {
        user_id: targetUserId,
        is_lead: Boolean(draft?.is_lead),
      });
      setNotice({ type: "ok", text: "Updated support group members." });
      await loadAll();
    } catch (err: unknown) {
      showError(err, "Failed to add member.");
    }
  };

  const handleRemoveMember = async (groupId: string, userId: string) => {
    setNotice(null);
    try {
      await api.adminRemoveGroupMember(groupId, userId);
      await loadAll();
    } catch (err: unknown) {
      showError(err, "Failed to remove member.");
    }
  };

  const handleCreateCategory = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newCatName.trim() || !newCatSlug.trim()) return;
    setNotice(null);
    try {
      await api.adminCreateCategory({
        name: newCatName.trim(),
        slug: newCatSlug.trim().toLowerCase(),
        default_group_id: newCatGroupId || groups[0]?.id || null,
        default_priority: newCatPriority,
      });
      setNewCatName("");
      setNewCatSlug("");
      setNotice({ type: "ok", text: "Created category." });
      await loadAll();
    } catch (err: unknown) {
      showError(err, "Failed to create category.");
    }
  };

  const handleUpdateCategory = async (
    categoryId: string,
    patch: Parameters<typeof api.adminUpdateCategory>[1]
  ) => {
    setNotice(null);
    try {
      await api.adminUpdateCategory(categoryId, patch);
      await loadAll();
    } catch (err: unknown) {
      showError(err, "Failed to update category.");
    }
  };

  /* ===== Users & Departments ===== */
  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setNotice(null);
    try {
      await api.adminCreateUser({
        username: newUserUsername.trim(),
        full_name: newUserFullName.trim(),
        email: newUserEmail.trim(),
        password: newUserPassword,
        role: newUserRole,
        department_id: newUserDeptId || null,
      });
      setNewUserUsername("");
      setNewUserFullName("");
      setNewUserEmail("");
      setNewUserPassword("Password123!");
      setNotice({ type: "ok", text: "Created local user account." });
      await loadAll();
    } catch (err: unknown) {
      showError(err, "Failed to create user.");
    }
  };

  const handleUpdateUser = async (
    userId: string,
    patch: Parameters<typeof api.adminUpdateUser>[1]
  ) => {
    setNotice(null);
    try {
      await api.adminUpdateUser(userId, patch);
      setNotice({ type: "ok", text: "Updated user." });
      await loadAll();
    } catch (err: unknown) {
      showError(err, "Failed to update user.");
    }
  };

  const handleCreateDepartment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newDeptCode.trim() || !newDeptName.trim()) return;
    setNotice(null);
    try {
      await api.adminCreateDepartment({
        code: newDeptCode.trim().toUpperCase(),
        name: newDeptName.trim(),
      });
      setNewDeptCode("");
      setNewDeptName("");
      setNotice({ type: "ok", text: "Created department." });
      await loadAll();
    } catch (err: unknown) {
      showError(err, "Failed to create department.");
    }
  };

  const handleRetryOutbox = async (eventId: string) => {
    await api.adminRetryOutboxEvent(eventId);
    await loadAll();
  };

  const handleCreateMacro = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newMacroShortcut.trim() || !newMacroTitle.trim() || !newMacroBody.trim()) return;
    setNotice(null);
    try {
      await api.createMacro({
        shortcut: newMacroShortcut.trim(),
        title: newMacroTitle.trim(),
        body: newMacroBody.trim(),
        target_status: newMacroStatus || null,
        is_internal: newMacroInternal,
      });
      setNewMacroShortcut("");
      setNewMacroTitle("");
      setNewMacroBody("");
      setNewMacroStatus("");
      setNewMacroInternal(false);
      setNotice({ type: "ok", text: "Created canned response macro." });
      await loadAll();
    } catch (err: unknown) {
      showError(err, "Failed to create macro.");
    }
  };

  const handleDeleteMacro = async (macroId: string) => {
    setNotice(null);
    try {
      await api.deleteMacro(macroId);
      setNotice({ type: "ok", text: "Deleted macro." });
      await loadAll();
    } catch (err: unknown) {
      showError(err, "Failed to delete macro.");
    }
  };

  const internalKbCount = kbArticles.filter((a) => a.visibility === "INTERNAL").length;
  const publicKbCount = kbArticles.filter((a) => a.visibility === "PUBLIC").length;

  const tabs: Array<{ id: AdminTab; label: string }> = [
    { id: "general", label: "General & SLA" },
    { id: "groups", label: "Groups & Categories" },
    { id: "users", label: "Users & Departments" },
    { id: "macros", label: `Macros (${macros.length})` },
    { id: "outbox", label: `Outbox Log (${outbox.length})` },
  ];

  return (
    <AppShell>
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-[17px] leading-[22px] font-medium text-foreground">
              System Settings, SLA, Teams &amp; Outbox
            </h1>
            <p className="text-meta">
              Configure automation, SLA targets, work calendar, support groups, users, and n8n webhook delivery
            </p>
          </div>
          <Button variant="outline" onClick={() => void loadAll()}>
            <RefreshCw className="size-3.5" strokeWidth={1.5} />
            <span>Refresh</span>
          </Button>
        </div>

        {/* Section Tabs */}
        <div className="flex flex-wrap items-center gap-1 border-b border-border pb-2">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                "h-8 px-3 rounded-sm text-[13px] font-medium border transition-colors duration-75",
                activeTab === tab.id
                  ? "bg-card text-foreground border-border"
                  : "bg-transparent text-muted-foreground border-transparent hover:bg-muted/60 hover:text-foreground"
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {notice && (
          <div
            className={cn(
              "rounded-md border px-3.5 py-2 text-[13px] flex items-center justify-between gap-3",
              notice.type === "err"
                ? "border-destructive/30 bg-destructive/5 text-destructive"
                : "border-border bg-card text-foreground"
            )}
          >
            <span>{notice.text}</span>
            <button
              type="button"
              onClick={() => setNotice(null)}
              className="text-faint hover:text-foreground"
            >
              <X className="size-3.5" />
            </button>
          </div>
        )}

        {loading ? (
          <div className="rounded-lg border border-border bg-card overflow-hidden">
            <SkeletonRow count={4} compact />
          </div>
        ) : activeTab === "general" ? (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
            <div className="lg:col-span-6 space-y-4">
              {/* Automation Settings */}
              <div className="rounded-lg border border-border bg-card overflow-hidden">
                <div className="h-10 px-4 border-b border-border bg-background flex items-center justify-between">
                  <span className="text-body-strong">Automation (Persisted in DB)</span>
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
                </div>
              </div>

              {/* Knowledge Base Summary */}
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

              {/* Editable SLA Policies */}
              <div className="rounded-lg border border-border bg-card overflow-hidden">
                <div className="h-10 px-4 border-b border-border bg-background flex items-center justify-between">
                  <span className="text-body-strong">SLA Policies</span>
                  <span className="text-meta tabular-nums">{slas.length}</span>
                </div>
                <div className="divide-y divide-border-subtle">
                  {slas.map((s) => {
                    const draft = slaDrafts[s.id];
                    if (!draft) return null;
                    return (
                      <div key={s.id} className="p-3.5 space-y-2.5">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-body-strong">{s.name}</span>
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={() => void handleSaveSlaPolicy(s.id)}
                          >
                            Save
                          </Button>
                        </div>
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 items-end">
                          <label className="space-y-1">
                            <span className="block text-[11px] text-meta">Response (m)</span>
                            <input
                              type="number"
                              min={1}
                              value={draft.first_response_minutes}
                              onChange={(e) =>
                                setSlaDrafts((prev) => ({
                                  ...prev,
                                  [s.id]: {
                                    ...prev[s.id],
                                    first_response_minutes: Math.max(1, Number(e.target.value) || 1),
                                  },
                                }))
                              }
                              className="w-full h-8 rounded-md border border-input bg-card px-2 text-[13px] tabular-nums"
                            />
                          </label>
                          <label className="space-y-1">
                            <span className="block text-[11px] text-meta">Resolve (m)</span>
                            <input
                              type="number"
                              min={1}
                              value={draft.resolution_minutes}
                              onChange={(e) =>
                                setSlaDrafts((prev) => ({
                                  ...prev,
                                  [s.id]: {
                                    ...prev[s.id],
                                    resolution_minutes: Math.max(1, Number(e.target.value) || 1),
                                  },
                                }))
                              }
                              className="w-full h-8 rounded-md border border-input bg-card px-2 text-[13px] tabular-nums"
                            />
                          </label>
                          <label className="space-y-1">
                            <span className="block text-[11px] text-meta">Warn (%)</span>
                            <input
                              type="number"
                              min={10}
                              max={99}
                              value={draft.warning_threshold_pct}
                              onChange={(e) =>
                                setSlaDrafts((prev) => ({
                                  ...prev,
                                  [s.id]: {
                                    ...prev[s.id],
                                    warning_threshold_pct: Math.min(
                                      99,
                                      Math.max(10, Number(e.target.value) || 80)
                                    ),
                                  },
                                }))
                              }
                              className="w-full h-8 rounded-md border border-input bg-card px-2 text-[13px] tabular-nums"
                            />
                          </label>
                          <div className="h-8 flex items-center gap-2">
                            <Checkbox
                              checked={draft.business_hours_only}
                              onChange={(next) =>
                                setSlaDrafts((prev) => ({
                                  ...prev,
                                  [s.id]: { ...prev[s.id], business_hours_only: next },
                                }))
                              }
                              ariaLabel={`Business hours only for ${s.name}`}
                            />
                            <span className="text-[12px] text-muted-foreground">Biz hours</span>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* Right column: Business Calendar */}
            <div className="lg:col-span-6 space-y-4">
              {calendar && (
                <form
                  onSubmit={handleSaveCalendar}
                  className="rounded-lg border border-border bg-card overflow-hidden"
                >
                  <div className="h-10 px-4 border-b border-border bg-background flex items-center justify-between">
                    <span className="text-body-strong">Business Calendar &amp; Holidays</span>
                    <Button type="submit" variant="primary" size="sm">
                      Save Calendar
                    </Button>
                  </div>

                  <div className="p-4 space-y-4">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <label className="space-y-1">
                        <span className="block text-meta">Calendar name</span>
                        <input
                          type="text"
                          value={calName}
                          onChange={(e) => setCalName(e.target.value)}
                          className={cn(inputBaseClass, "h-8 text-[13px]")}
                        />
                      </label>
                      <label className="space-y-1">
                        <span className="block text-meta">Timezone</span>
                        <input
                          type="text"
                          value={calTz}
                          onChange={(e) => setCalTz(e.target.value)}
                          className={cn(inputBaseClass, "h-8 text-[13px] font-mono")}
                        />
                      </label>
                    </div>

                    <div className="space-y-1.5">
                      <span className="block text-meta">Working hours by weekday</span>
                      <div className="divide-y divide-border-subtle rounded-md border border-border overflow-hidden">
                        {WEEKDAYS.map((day) => {
                          const win = calWorkDays[day.key];
                          const enabled = Boolean(win);
                          return (
                            <div
                              key={day.key}
                              className="px-3 py-2 flex items-center justify-between gap-3 bg-card"
                            >
                              <div className="flex items-center gap-2.5 min-w-[88px]">
                                <Checkbox
                                  checked={enabled}
                                  onChange={(next) => handleToggleWorkDay(day.key, next)}
                                  ariaLabel={`Toggle ${day.label}`}
                                />
                                <span className="text-[13px] font-medium text-foreground">
                                  {day.label}
                                </span>
                              </div>
                              {enabled && win ? (
                                <div className="flex items-center gap-2">
                                  <input
                                    type="time"
                                    value={win[0]}
                                    onChange={(e) =>
                                      handleWorkDayTime(day.key, 0, e.target.value)
                                    }
                                    className="h-7 rounded-md border border-input bg-card px-2 text-[13px] tabular-nums"
                                  />
                                  <span className="text-meta">–</span>
                                  <input
                                    type="time"
                                    value={win[1]}
                                    onChange={(e) =>
                                      handleWorkDayTime(day.key, 1, e.target.value)
                                    }
                                    className="h-7 rounded-md border border-input bg-card px-2 text-[13px] tabular-nums"
                                  />
                                </div>
                              ) : (
                                <span className="text-meta-faint">Day off</span>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>

                    <div className="space-y-2">
                      <span className="block text-meta">Holidays ({calHolidays.length})</span>
                      <div className="flex items-center gap-2">
                        <input
                          type="date"
                          value={newHolidayDate}
                          onChange={(e) => setNewHolidayDate(e.target.value)}
                          className="h-8 rounded-md border border-input bg-card px-2.5 text-[13px] tabular-nums"
                        />
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={handleAddHoliday}
                        >
                          <Plus className="size-3.5" />
                          <span>Add holiday</span>
                        </Button>
                      </div>
                      {calHolidays.length > 0 && (
                        <div className="flex flex-wrap gap-1.5 pt-1">
                          {calHolidays.map((d) => (
                            <span
                              key={d}
                              className="inline-flex items-center gap-1.5 h-6 px-2 rounded-sm border border-border bg-background text-[12px] font-mono text-foreground"
                            >
                              <span>{d}</span>
                              <button
                                type="button"
                                onClick={() =>
                                  setCalHolidays((prev) => prev.filter((item) => item !== d))
                                }
                                className="text-faint hover:text-destructive"
                                aria-label={`Remove holiday ${d}`}
                              >
                                <X className="size-3" />
                              </button>
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </form>
              )}
            </div>
          </div>
        ) : activeTab === "groups" ? (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
            {/* Support Groups & Members */}
            <div className="lg:col-span-6 rounded-lg border border-border bg-card overflow-hidden">
              <div className="h-10 px-4 border-b border-border bg-background flex items-center justify-between">
                <span className="text-body-strong">Support Groups &amp; Members</span>
                <span className="text-meta tabular-nums">{groups.length}</span>
              </div>

              <div className="divide-y divide-border-subtle">
                {groups.map((grp) => {
                  const draft = memberDrafts[grp.id] || {
                    user_id: activeItUsers[0]?.id || "",
                    is_lead: false,
                  };
                  return (
                    <div key={grp.id} className="p-4 space-y-2.5">
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <p className="text-body-strong">
                            {grp.name}{" "}
                            <span className="text-meta font-mono">({grp.code})</span>
                          </p>
                          {grp.description && (
                            <p className="text-meta">{grp.description}</p>
                          )}
                        </div>
                        <span className="text-meta tabular-nums">
                          {grp.members.length} member(s)
                        </span>
                      </div>

                      {grp.members.length > 0 && (
                        <div className="flex flex-wrap gap-1.5">
                          {grp.members.map((m) => (
                            <span
                              key={m.id}
                              className="inline-flex items-center gap-1.5 h-6 px-2 rounded-sm border border-border bg-background text-[12px] text-foreground"
                            >
                              <span>{m.user.full_name}</span>
                              {m.is_lead && (
                                <span className="text-[10px] font-medium px-1 rounded-xs bg-muted text-muted-foreground">
                                  Lead
                                </span>
                              )}
                              <button
                                type="button"
                                onClick={() => void handleRemoveMember(grp.id, m.user_id)}
                                className="text-faint hover:text-destructive"
                                title="Remove from group"
                              >
                                <X className="size-3" />
                              </button>
                            </span>
                          ))}
                        </div>
                      )}

                      <div className="flex flex-wrap items-center gap-2 pt-1">
                        <select
                          value={draft.user_id}
                          onChange={(e) =>
                            setMemberDrafts((prev) => ({
                              ...prev,
                              [grp.id]: { ...draft, user_id: e.target.value },
                            }))
                          }
                          className={cn(selectBaseClass, "flex-1 min-w-[160px]")}
                        >
                          {activeItUsers.map((u) => (
                            <option key={u.id} value={u.id}>
                              {u.full_name} ({u.username})
                            </option>
                          ))}
                        </select>
                        <label className="inline-flex items-center gap-1.5 text-[12px] text-muted-foreground">
                          <Checkbox
                            checked={draft.is_lead}
                            onChange={(next) =>
                              setMemberDrafts((prev) => ({
                                ...prev,
                                [grp.id]: { ...draft, is_lead: next },
                              }))
                            }
                            ariaLabel={`Set lead for ${grp.name}`}
                          />
                          <span>Lead</span>
                        </label>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => void handleAddMember(grp.id)}
                        >
                          Add member
                        </Button>
                      </div>
                    </div>
                  );
                })}
              </div>

              <form
                onSubmit={handleCreateGroup}
                className="p-3 border-t border-border bg-background grid grid-cols-1 sm:grid-cols-[110px_1fr_auto] gap-2"
              >
                <input
                  type="text"
                  required
                  value={newGroupCode}
                  onChange={(e) => setNewGroupCode(e.target.value)}
                  placeholder="GRP_CODE"
                  className={cn(inputBaseClass, "h-8 text-[13px] font-mono uppercase")}
                />
                <input
                  type="text"
                  required
                  value={newGroupName}
                  onChange={(e) => setNewGroupName(e.target.value)}
                  placeholder="New support group name"
                  className={cn(inputBaseClass, "h-8 text-[13px]")}
                />
                <Button type="submit" variant="primary" size="sm">
                  Add group
                </Button>
              </form>
            </div>

            {/* Categories */}
            <div className="lg:col-span-6 rounded-lg border border-border bg-card overflow-hidden">
              <div className="h-10 px-4 border-b border-border bg-background flex items-center justify-between">
                <span className="text-body-strong">Categories</span>
                <span className="text-meta tabular-nums">{categories.length}</span>
              </div>

              <div className="divide-y divide-border-subtle">
                {categories.map((c) => (
                  <div key={c.id} className="px-4 py-2.5 space-y-2">
                    <div className="flex items-center justify-between gap-2">
                      <div className="min-w-0">
                        <p className="text-body-strong truncate">{c.name}</p>
                        <p className="text-meta-faint font-mono truncate">{c.slug}</p>
                      </div>
                      <label className="inline-flex items-center gap-1.5 text-[12px] text-muted-foreground">
                        <Checkbox
                          checked={c.is_active}
                          onChange={(next) =>
                            void handleUpdateCategory(c.id, { is_active: next })
                          }
                          ariaLabel={`Toggle active for ${c.name}`}
                        />
                        <span>Active</span>
                      </label>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <select
                        value={c.default_group_id || ""}
                        onChange={(e) =>
                          void handleUpdateCategory(c.id, {
                            default_group_id: e.target.value || null,
                          })
                        }
                        className={selectBaseClass}
                      >
                        <option value="">No default group</option>
                        {groups.map((g) => (
                          <option key={g.id} value={g.id}>
                            {g.name}
                          </option>
                        ))}
                      </select>
                      <select
                        value={c.default_priority}
                        onChange={(e) =>
                          void handleUpdateCategory(c.id, {
                            default_priority: e.target.value as TicketPriority,
                          })
                        }
                        className={selectBaseClass}
                      >
                        <option value="LOW">Low</option>
                        <option value="MEDIUM">Medium</option>
                        <option value="HIGH">High</option>
                        <option value="CRITICAL">Urgent</option>
                      </select>
                    </div>
                  </div>
                ))}
              </div>

              <form
                onSubmit={handleCreateCategory}
                className="p-3 border-t border-border bg-background space-y-2"
              >
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  <input
                    type="text"
                    required
                    value={newCatName}
                    onChange={(e) => setNewCatName(e.target.value)}
                    placeholder="Category name"
                    className={cn(inputBaseClass, "h-8 text-[13px]")}
                  />
                  <input
                    type="text"
                    required
                    value={newCatSlug}
                    onChange={(e) => setNewCatSlug(e.target.value)}
                    placeholder="slug-name"
                    className={cn(inputBaseClass, "h-8 text-[13px] font-mono")}
                  />
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <select
                    value={newCatGroupId}
                    onChange={(e) => setNewCatGroupId(e.target.value)}
                    className={cn(selectBaseClass, "flex-1 min-w-[150px]")}
                  >
                    {groups.map((g) => (
                      <option key={g.id} value={g.id}>
                        {g.name}
                      </option>
                    ))}
                  </select>
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
                  <Button type="submit" variant="primary" size="sm">
                    Add category
                  </Button>
                </div>
              </form>
            </div>
          </div>
        ) : activeTab === "users" ? (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
            {/* Users */}
            <div className="lg:col-span-8 rounded-lg border border-border bg-card overflow-hidden">
              <div className="h-10 px-4 border-b border-border bg-background flex items-center justify-between gap-3">
                <span className="text-body-strong">
                  Users (LDAP / AD &amp; Local) · {filteredUsers.length}
                </span>
                <div className="relative w-56">
                  <Search className="size-3.5 text-faint absolute left-2.5 top-2" />
                  <input
                    type="text"
                    value={userSearch}
                    onChange={(e) => setUserSearch(e.target.value)}
                    placeholder="Search user..."
                    className="w-full h-7 pl-8 pr-2.5 rounded-md border border-input bg-card text-[12px] text-foreground"
                  />
                </div>
              </div>

              {user?.role === "SYS_ADMIN" && (
                <form
                  onSubmit={handleCreateUser}
                  className="p-3.5 border-b border-border bg-background/60 space-y-2"
                >
                  <p className="text-[12px] font-medium text-foreground">
                    Create local account
                  </p>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                    <input
                      type="text"
                      required
                      value={newUserUsername}
                      onChange={(e) => setNewUserUsername(e.target.value)}
                      placeholder="username"
                      className={cn(inputBaseClass, "h-8 text-[13px] font-mono")}
                    />
                    <input
                      type="text"
                      required
                      value={newUserFullName}
                      onChange={(e) => setNewUserFullName(e.target.value)}
                      placeholder="Full name"
                      className={cn(inputBaseClass, "h-8 text-[13px]")}
                    />
                    <input
                      type="email"
                      required
                      value={newUserEmail}
                      onChange={(e) => setNewUserEmail(e.target.value)}
                      placeholder="email@company.local"
                      className={cn(inputBaseClass, "h-8 text-[13px]")}
                    />
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <input
                      type="password"
                      required
                      minLength={6}
                      value={newUserPassword}
                      onChange={(e) => setNewUserPassword(e.target.value)}
                      placeholder="Password"
                      className={cn(inputBaseClass, "h-8 text-[13px] w-40")}
                    />
                    <select
                      value={newUserRole}
                      onChange={(e) => setNewUserRole(e.target.value as UserRole)}
                      className={selectBaseClass}
                    >
                      <option value="END_USER">End user</option>
                      <option value="IT_AGENT">IT Agent</option>
                      <option value="IT_LEAD">IT Lead</option>
                      <option value="SYS_ADMIN">Sys Admin</option>
                    </select>
                    <select
                      value={newUserDeptId}
                      onChange={(e) => setNewUserDeptId(e.target.value)}
                      className={selectBaseClass}
                    >
                      <option value="">No department</option>
                      {departments.map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.name}
                        </option>
                      ))}
                    </select>
                    <Button type="submit" variant="primary" size="sm">
                      Create user
                    </Button>
                  </div>
                </form>
              )}

              <div className="divide-y divide-border-subtle">
                {filteredUsers.map((u) => {
                  const chDraft = userChannelDrafts[u.id] || {
                    telegram_chat_id: "",
                    zalo_user_id: "",
                  };
                  return (
                    <div key={u.id} className="px-4 py-3 space-y-2">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="min-w-0">
                          <p className="text-body-strong truncate">
                            {u.full_name}{" "}
                            <span className="text-meta font-mono">({u.username})</span>
                          </p>
                          <p className="text-meta-faint truncate">{u.email}</p>
                        </div>
                        {user?.role === "SYS_ADMIN" ? (
                          <div className="flex flex-wrap items-center gap-2">
                            <select
                              value={u.department_id || ""}
                              onChange={(e) =>
                                void handleUpdateUser(u.id, {
                                  department_id: e.target.value || null,
                                })
                              }
                              className={selectBaseClass}
                            >
                              <option value="">No dept</option>
                              {departments.map((d) => (
                                <option key={d.id} value={d.id}>
                                  {d.name}
                                </option>
                              ))}
                            </select>
                            <select
                              value={u.role}
                              onChange={(e) =>
                                void handleUpdateUser(u.id, {
                                  role: e.target.value as UserRole,
                                })
                              }
                              className={selectBaseClass}
                            >
                              <option value="END_USER">End user</option>
                              <option value="IT_AGENT">IT Agent</option>
                              <option value="IT_LEAD">IT Lead</option>
                              <option value="SYS_ADMIN">Sys Admin</option>
                            </select>
                            <label className="inline-flex items-center gap-1.5 text-[12px] text-muted-foreground">
                              <Checkbox
                                checked={u.is_active}
                                onChange={(next) =>
                                  void handleUpdateUser(u.id, { is_active: next })
                                }
                                ariaLabel={`Toggle active for ${u.username}`}
                              />
                              <span>Active</span>
                            </label>
                          </div>
                        ) : (
                          <span className="text-meta">{ROLE_LABELS[u.role]}</span>
                        )}
                      </div>

                      {user?.role === "SYS_ADMIN" && (
                        <div className="flex flex-wrap items-center gap-2">
                          <input
                            type="text"
                            value={chDraft.telegram_chat_id}
                            onChange={(e) =>
                              setUserChannelDrafts((prev) => ({
                                ...prev,
                                [u.id]: { ...chDraft, telegram_chat_id: e.target.value },
                              }))
                            }
                            placeholder="Telegram Chat ID"
                            className="h-7 w-44 rounded-md border border-input bg-card px-2 text-[12px] font-mono"
                          />
                          <input
                            type="text"
                            value={chDraft.zalo_user_id}
                            onChange={(e) =>
                              setUserChannelDrafts((prev) => ({
                                ...prev,
                                [u.id]: { ...chDraft, zalo_user_id: e.target.value },
                              }))
                            }
                            placeholder="Zalo User ID"
                            className="h-7 w-44 rounded-md border border-input bg-card px-2 text-[12px] font-mono"
                          />
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={() =>
                              void handleUpdateUser(u.id, {
                                telegram_chat_id: chDraft.telegram_chat_id.trim() || null,
                                zalo_user_id: chDraft.zalo_user_id.trim() || null,
                              })
                            }
                          >
                            Save IDs
                          </Button>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Departments */}
            <div className="lg:col-span-4 rounded-lg border border-border bg-card overflow-hidden">
              <div className="h-10 px-4 border-b border-border bg-background flex items-center justify-between">
                <span className="text-body-strong">Departments</span>
                <span className="text-meta tabular-nums">{departments.length}</span>
              </div>
              <div className="divide-y divide-border-subtle">
                {departments.map((d) => (
                  <div
                    key={d.id}
                    className="px-4 py-2.5 flex items-center justify-between gap-2"
                  >
                    <div className="min-w-0">
                      <p className="text-body-strong truncate">{d.name}</p>
                      <p className="text-meta-faint font-mono">{d.code}</p>
                    </div>
                    <Checkbox
                      checked={d.is_active}
                      onChange={(next) =>
                        void api
                          .adminUpdateDepartment(d.id, { is_active: next })
                          .then(() => loadAll())
                      }
                      ariaLabel={`Toggle active for ${d.name}`}
                    />
                  </div>
                ))}
              </div>
              <form
                onSubmit={handleCreateDepartment}
                className="p-3 border-t border-border bg-background space-y-2"
              >
                <div className="grid grid-cols-[90px_1fr] gap-2">
                  <input
                    type="text"
                    required
                    value={newDeptCode}
                    onChange={(e) => setNewDeptCode(e.target.value)}
                    placeholder="CODE"
                    className={cn(inputBaseClass, "h-8 text-[13px] font-mono uppercase")}
                  />
                  <input
                    type="text"
                    required
                    value={newDeptName}
                    onChange={(e) => setNewDeptName(e.target.value)}
                    placeholder="Department name"
                    className={cn(inputBaseClass, "h-8 text-[13px]")}
                  />
                </div>
                <Button type="submit" variant="primary" size="sm" className="w-full">
                  Add department
                </Button>
              </form>
            </div>
          </div>
        ) : activeTab === "macros" ? (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
            <div className="lg:col-span-7 rounded-lg border border-border bg-card overflow-hidden">
              <div className="h-10 px-4 border-b border-border bg-background flex items-center justify-between">
                <span className="text-body-strong">Canned Responses / Macros</span>
                <span className="text-meta tabular-nums">{macros.length}</span>
              </div>
              <div className="divide-y divide-border-subtle">
                {macros.map((m) => (
                  <div key={m.id} className="px-4 py-3 flex items-start justify-between gap-3">
                    <div className="min-w-0 space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-[12px] font-mono font-medium px-1.5 py-0.5 rounded-xs bg-muted text-foreground">
                          /{m.shortcut}
                        </span>
                        <span className="text-body-strong">{m.title}</span>
                        {m.is_internal && (
                          <span className="text-[11px] px-1.5 py-0.5 rounded-xs bg-note border border-note-border text-note-ink">
                            Internal note
                          </span>
                        )}
                        {m.target_status && (
                          <span className="text-[11px] px-1.5 py-0.5 rounded-xs border border-border text-muted-foreground font-mono">
                            → {m.target_status}
                          </span>
                        )}
                      </div>
                      <p className="text-meta whitespace-pre-wrap">{m.body}</p>
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => void handleDeleteMacro(m.id)}
                    >
                      Delete
                    </Button>
                  </div>
                ))}
              </div>
            </div>

            <form
              onSubmit={handleCreateMacro}
              className="lg:col-span-5 rounded-lg border border-border bg-card overflow-hidden"
            >
              <div className="h-10 px-4 border-b border-border bg-background flex items-center">
                <span className="text-body-strong">New Macro</span>
              </div>
              <div className="p-4 space-y-3">
                <div className="grid grid-cols-2 gap-2">
                  <label className="space-y-1">
                    <span className="block text-meta">Shortcut</span>
                    <input
                      type="text"
                      required
                      value={newMacroShortcut}
                      onChange={(e) => setNewMacroShortcut(e.target.value)}
                      placeholder="uv"
                      className={cn(inputBaseClass, "h-8 text-[13px] font-mono")}
                    />
                  </label>
                  <label className="space-y-1">
                    <span className="block text-meta">Auto status (optional)</span>
                    <select
                      value={newMacroStatus}
                      onChange={(e) => setNewMacroStatus(e.target.value as TicketStatus | "")}
                      className={cn(selectBaseClass, "w-full")}
                    >
                      <option value="">No status change</option>
                      <option value="IN_PROGRESS">In Progress</option>
                      <option value="WAITING_FOR_USER">Waiting on user</option>
                      <option value="RESOLVED">Resolved</option>
                    </select>
                  </label>
                </div>

                <label className="block space-y-1">
                  <span className="block text-meta">Title</span>
                  <input
                    type="text"
                    required
                    value={newMacroTitle}
                    onChange={(e) => setNewMacroTitle(e.target.value)}
                    placeholder="Xin UltraViewer..."
                    className={cn(inputBaseClass, "h-8 text-[13px]")}
                  />
                </label>

                <label className="block space-y-1">
                  <span className="block text-meta">Message body</span>
                  <textarea
                    required
                    rows={4}
                    value={newMacroBody}
                    onChange={(e) => setNewMacroBody(e.target.value)}
                    placeholder="Chào bạn..."
                    className={cn(inputBaseClass, "text-[13px]")}
                  />
                </label>

                <label className="inline-flex items-center gap-2 text-[13px] text-foreground">
                  <Checkbox
                    checked={newMacroInternal}
                    onChange={setNewMacroInternal}
                    ariaLabel="Macro is internal note"
                  />
                  <span>Insert as Internal note</span>
                </label>

                <Button type="submit" variant="primary" className="w-full">
                  Create Macro
                </Button>
              </div>
            </form>
          </div>
        ) : (
          /* Outbox Log */
          <div className="rounded-lg border border-border bg-card overflow-hidden">
            <div className="h-10 px-4 border-b border-border bg-background flex items-center justify-between gap-3">
              <span className="text-body-strong">Transactional Outbox (n8n)</span>
              <div className="flex items-center gap-1">
                {(["ALL", "PENDING", "SENT", "FAILED"] as const).map((st) => (
                  <button
                    key={st}
                    type="button"
                    onClick={() => setOutboxFilter(st)}
                    className={cn(
                      "h-6 px-2 rounded-xs text-[12px] font-medium",
                      outboxFilter === st
                        ? "bg-muted text-foreground"
                        : "text-muted-foreground hover:text-foreground"
                    )}
                  >
                    {st}
                  </button>
                ))}
              </div>
            </div>
            <div className="max-h-[540px] overflow-y-auto divide-y divide-border-subtle">
              {filteredOutbox.map((ev) => (
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
                        className={`inline-flex h-5 items-center rounded-sm px-1.5 text-[12px] font-medium ${ev.status === "SENT"
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
        )}
      </div>
    </AppShell>
  );
}
