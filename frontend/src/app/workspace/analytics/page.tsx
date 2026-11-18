"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Download, FileJson, FileSpreadsheet, Loader2 } from "lucide-react";

import { AppShell } from "@/components/AppShell";
import { DonutChart, GaugeRing, TrendChart } from "@/components/charts";
import { Button, SkeletonRow, selectBaseClass } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { PRIORITY_LABELS, STATUS_LABELS } from "@/lib/formatters";
import {
  AnalyticsSummary,
  SupportGroup,
  TicketPriority,
  TicketStatus,
} from "@/lib/types";

const DONUT_RAMP = ["#17181C", "#6B6F77", "#9A9EA5", "#C9C8C3", "#3B6FE0", "#F8B99D"];
const STATUS_COLORS: Record<string, string> = {
  NEW: "#3B6FE0",
  ASSIGNED: "#6B6F77",
  IN_PROGRESS: "#17181C",
  WAITING_FOR_USER: "#F8B99D",
  RESOLVED: "#2FC98E",
  CLOSED: "#C9C8C3",
  REOPENED: "#EE9B3B",
  CANCELLED: "#9A9EA5",
};
const PRIORITY_COLORS: Record<TicketPriority, string> = {
  CRITICAL: "#D6453D",
  HIGH: "#EE9B3B",
  MEDIUM: "#6B6F77",
  LOW: "#C9C8C3",
};

type DatePreset = "7D" | "30D" | "ALL" | "CUSTOM";

function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

export default function AnalyticsPage() {
  const [data, setData] = useState<AnalyticsSummary | null>(null);
  const [groups, setGroups] = useState<SupportGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState<"csv" | "xlsx" | "json" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [preset, setPreset] = useState<DatePreset>("ALL");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [groupId, setGroupId] = useState("");
  const [priority, setPriority] = useState<TicketPriority | "">("");

  useEffect(() => {
    api
      .getMetadata()
      .then((m) => setGroups(m.support_groups))
      .catch(() => setGroups([]));
  }, []);

  const loadSummary = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getAnalyticsSummary({
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        support_group_id: groupId || undefined,
        priority: priority || undefined,
      });
      setData(res);
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Không thể tải dữ liệu thống kê."
      );
    } finally {
      setLoading(false);
    }
  }, [dateFrom, dateTo, groupId, priority]);

  useEffect(() => {
    void loadSummary();
  }, [loadSummary]);

  const applyPreset = (next: DatePreset) => {
    setPreset(next);
    if (next === "ALL") {
      setDateFrom("");
      setDateTo("");
    } else if (next === "7D") {
      setDateFrom(isoDaysAgo(7));
      setDateTo(isoDaysAgo(0));
    } else if (next === "30D") {
      setDateFrom(isoDaysAgo(30));
      setDateTo(isoDaysAgo(0));
    }
  };

  const handleExport = async (fmt: "csv" | "xlsx" | "json") => {
    setExporting(fmt);
    setError(null);
    try {
      await api.exportAnalyticsReport(fmt, {
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        support_group_id: groupId || undefined,
        priority: priority || undefined,
      });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Export thất bại.");
    } finally {
      setExporting(null);
    }
  };

  const maxDailyCount = data?.daily_trend.length
    ? Math.max(
        1,
        ...data.daily_trend.map((d) => Math.max(d.created_count, d.resolved_count))
      )
    : 1;

  return (
    <AppShell>
      <div className="space-y-4">
        {/* Header & Export Toolbar */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
          <div>
            <h1 className="text-[17px] leading-[22px] font-medium text-foreground">
              Analytics &amp; Operations Reports
            </h1>
            <p className="text-meta">
              SLA compliance, agent workload, daily trend, and multi-format export
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="outline"
              disabled={exporting !== null}
              onClick={() => void handleExport("csv")}
            >
              {exporting === "csv" ? (
                <Loader2 className="size-3.5 animate-spin" strokeWidth={1.5} />
              ) : (
                <Download className="size-3.5" strokeWidth={1.5} />
              )}
              <span>Export CSV</span>
            </Button>

            <Button
              variant="outline"
              disabled={exporting !== null}
              onClick={() => void handleExport("xlsx")}
            >
              {exporting === "xlsx" ? (
                <Loader2 className="size-3.5 animate-spin" strokeWidth={1.5} />
              ) : (
                <FileSpreadsheet className="size-3.5" strokeWidth={1.5} />
              )}
              <span>Export Excel (.xlsx)</span>
            </Button>

            <Button
              variant="outline"
              disabled={exporting !== null}
              onClick={() => void handleExport("json")}
            >
              {exporting === "json" ? (
                <Loader2 className="size-3.5 animate-spin" strokeWidth={1.5} />
              ) : (
                <FileJson className="size-3.5" strokeWidth={1.5} />
              )}
              <span>Export JSON</span>
            </Button>
          </div>
        </div>

        {/* Filter Bar */}
        <div className="rounded-lg border border-border bg-card px-4 py-2.5 flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-1">
            {(
              [
                { id: "7D", label: "7 days" },
                { id: "30D", label: "30 days" },
                { id: "ALL", label: "All time" },
              ] as Array<{ id: DatePreset; label: string }>
            ).map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => applyPreset(p.id)}
                className={cn(
                  "h-8 px-2.5 rounded-sm text-[13px] font-medium border transition-colors duration-75",
                  preset === p.id
                    ? "bg-muted text-foreground border-border"
                    : "bg-transparent text-muted-foreground border-transparent hover:bg-muted/60 hover:text-foreground"
                )}
              >
                {p.label}
              </button>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <input
              type="date"
              aria-label="Date from"
              value={dateFrom}
              onChange={(e) => {
                setPreset("CUSTOM");
                setDateFrom(e.target.value);
              }}
              className="h-8 rounded-md border border-input bg-card px-2.5 text-[13px] text-foreground tabular-nums focus:outline-none focus:border-foreground/30 focus:ring-2 focus:ring-ring/20"
            />
            <span className="text-meta-faint">to</span>
            <input
              type="date"
              aria-label="Date to"
              value={dateTo}
              onChange={(e) => {
                setPreset("CUSTOM");
                setDateTo(e.target.value);
              }}
              className="h-8 rounded-md border border-input bg-card px-2.5 text-[13px] text-foreground tabular-nums focus:outline-none focus:border-foreground/30 focus:ring-2 focus:ring-ring/20"
            />

            <select
              aria-label="Filter by support group"
              value={groupId}
              onChange={(e) => setGroupId(e.target.value)}
              className={selectBaseClass}
            >
              <option value="">All groups</option>
              {groups.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
            </select>

            <select
              aria-label="Filter by priority"
              value={priority}
              onChange={(e) => setPriority(e.target.value as TicketPriority | "")}
              className={selectBaseClass}
            >
              <option value="">All priorities</option>
              <option value="CRITICAL">Urgent</option>
              <option value="HIGH">High</option>
              <option value="MEDIUM">Medium</option>
              <option value="LOW">Low</option>
            </select>
          </div>
        </div>

        {error && (
          <div className="rounded-md border border-destructive/30 bg-destructive/5 px-4 py-2.5 text-[13px] text-destructive">
            {error}
          </div>
        )}

        {loading || !data ? (
          <div className="rounded-lg border border-border bg-card overflow-hidden">
            <SkeletonRow count={4} compact />
          </div>
        ) : (
          <>
            {/* 5-Column KPI Strip */}
            <div className="anim-fade-up rounded-lg border border-border bg-card grid grid-cols-2 lg:grid-cols-5 divide-y lg:divide-y-0 lg:divide-x divide-border">
              <div className="p-4 space-y-1">
                <p className="text-meta">Total tickets</p>
                <p className="text-[17px] font-medium text-foreground tabular-nums">
                  {data.total_tickets}
                </p>
                <p className="text-meta-faint tabular-nums">
                  {data.open_tickets} open / {data.resolved_tickets} resolved
                </p>
              </div>

              <div className="p-4 space-y-1">
                <p className="text-meta">SLA compliance</p>
                <p className="text-[17px] font-medium text-foreground tabular-nums">
                  {data.sla_compliance_pct}%
                </p>
                <p className="text-meta-faint tabular-nums">
                  {data.breached_tickets} breached
                </p>
              </div>

              <div className="p-4 space-y-1">
                <p className="text-meta">Avg first response</p>
                <p className="text-[17px] font-medium text-foreground tabular-nums">
                  {data.avg_first_response_minutes}m
                </p>
                <p className="text-meta-faint">Mean time to first reply</p>
              </div>

              <div className="p-4 space-y-1">
                <p className="text-meta">Avg resolution (MTTR)</p>
                <p className="text-[17px] font-medium text-foreground tabular-nums">
                  {data.avg_resolution_minutes}m
                </p>
                <p className="text-meta-faint">Excludes paused user wait</p>
              </div>

              <div className="p-4 space-y-1">
                <p className="text-meta">Satisfaction (CSAT)</p>
                <p className="text-[17px] font-medium text-foreground tabular-nums">
                  {data.rated_count > 0 ? `${data.avg_rating}/5` : "—"}
                </p>
                <p className="text-meta-faint tabular-nums">
                  {data.rated_count} ratings
                </p>
              </div>
            </div>

            {/* Charts */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <div className="anim-fade-up lg:col-span-2 rounded-lg border border-border bg-card overflow-hidden">
                <div className="h-10 px-4 border-b border-border bg-background flex items-center justify-between">
                  <span className="text-body-strong">Daily volume trend</span>
                  <div className="flex items-center gap-3 text-meta">
                    <span className="inline-flex items-center gap-1.5">
                      <span className="size-2 rounded-[2px] bg-foreground" />
                      <span>Created</span>
                    </span>
                    <span className="inline-flex items-center gap-1.5">
                      <span className="size-2 rounded-[2px] bg-muted-foreground" />
                      <span>Resolved</span>
                    </span>
                    <span className="inline-flex items-center gap-1.5">
                      <span className="size-2 rounded-full bg-destructive" />
                      <span>SLA breach</span>
                    </span>
                  </div>
                </div>
                <TrendChart
                  data={data.daily_trend.map((d) => ({
                    date: d.date,
                    created: d.created_count,
                    resolved: d.resolved_count,
                    breached: d.breached_count,
                  }))}
                />
              </div>

              <div className="anim-fade-up rounded-lg border border-border bg-card overflow-hidden" style={{ animationDelay: "40ms" }}>
                <div className="h-10 px-4 border-b border-border bg-background flex items-center">
                  <span className="text-body-strong">SLA compliance</span>
                </div>
                <GaugeRing pct={data.sla_compliance_pct} label="on target" />
                <div className="px-4 pb-4 grid grid-cols-2 gap-2 text-[13px] tabular-nums">
                  <div className="rounded-sm border border-border-subtle px-2.5 py-1.5">
                    <p className="text-meta">Breached</p>
                    <p className="text-foreground font-medium">{data.breached_tickets}</p>
                  </div>
                  <div className="rounded-sm border border-border-subtle px-2.5 py-1.5">
                    <p className="text-meta">Within SLA</p>
                    <p className="text-foreground font-medium">
                      {Math.max(0, data.total_tickets - data.breached_tickets)}
                    </p>
                  </div>
                </div>
              </div>

              <div className="anim-fade-up rounded-lg border border-border bg-card overflow-hidden" style={{ animationDelay: "80ms" }}>
                <div className="h-10 px-4 border-b border-border bg-background flex items-center">
                  <span className="text-body-strong">Status distribution</span>
                </div>
                <DonutChart
                  centerLabel="tickets"
                  slices={Object.entries(data.by_status).map(([st, cnt], i) => ({
                    label: STATUS_LABELS[st as TicketStatus] || st,
                    value: cnt,
                    color: STATUS_COLORS[st] || DONUT_RAMP[i % DONUT_RAMP.length],
                  }))}
                />
              </div>

              <div className="anim-fade-up rounded-lg border border-border bg-card overflow-hidden" style={{ animationDelay: "120ms" }}>
                <div className="h-10 px-4 border-b border-border bg-background flex items-center">
                  <span className="text-body-strong">Priority mix</span>
                </div>
                <DonutChart
                  centerLabel="tickets"
                  slices={(["CRITICAL", "HIGH", "MEDIUM", "LOW"] as TicketPriority[])
                    .filter((p) => data.by_priority[p])
                    .map((p) => ({
                      label: PRIORITY_LABELS[p],
                      value: data.by_priority[p],
                      color: PRIORITY_COLORS[p],
                    }))}
                />
              </div>

              <div className="anim-fade-up rounded-lg border border-border bg-card overflow-hidden" style={{ animationDelay: "160ms" }}>
                <div className="h-10 px-4 border-b border-border bg-background flex items-center">
                  <span className="text-body-strong">Category share</span>
                </div>
                <DonutChart
                  centerLabel="tickets"
                  slices={data.by_category.slice(0, 6).map((row, i) => ({
                    label: row.name,
                    value: row.count,
                    color: DONUT_RAMP[i % DONUT_RAMP.length],
                  }))}
                />
              </div>
            </div>
            {/* 2x2 Breakdown Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {/* Agent Performance */}
              <div className="rounded-lg border border-border bg-card overflow-hidden">
                <div className="h-10 px-4 border-b border-border bg-background flex items-center justify-between">
                  <span className="text-body-strong">Agent workload &amp; SLA</span>
                  <span className="text-meta">Assigned / Resolved / Breached / MTTR</span>
                </div>
                <div className="divide-y divide-border-subtle">
                  {data.by_agent.map((ag) => (
                    <div
                      key={ag.agent_name}
                      className="px-4 py-2.5 flex items-center justify-between gap-3"
                    >
                      <span className="text-body truncate">{ag.agent_name}</span>
                      <div className="flex items-center gap-3 text-meta tabular-nums shrink-0">
                        <span className="text-foreground font-medium">
                          {ag.assigned_count}
                        </span>
                        <span>{ag.resolved_count} done</span>
                        <span
                          className={cn(
                            "px-1.5 py-0.5 rounded-sm text-[12px]",
                            ag.breached_count > 0
                              ? "bg-sla-breached text-sla-breached-fg"
                              : "bg-sla-neutral text-sla-neutral-fg"
                          )}
                        >
                          {ag.breached_count} breached
                        </span>
                        <span className="w-14 text-right">{ag.avg_resolution_minutes}m</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* By Category */}
              <div className="rounded-lg border border-border bg-card overflow-hidden">
                <div className="h-10 px-4 border-b border-border bg-background flex items-center justify-between">
                  <span className="text-body-strong">By category</span>
                  <span className="text-meta">Count</span>
                </div>
                <div className="divide-y divide-border-subtle">
                  {data.by_category.map((row) => {
                    const pct = data.total_tickets
                      ? Math.round((row.count / data.total_tickets) * 100)
                      : 0;
                    return (
                      <div key={row.name} className="px-4 py-2.5 space-y-1">
                        <div className="flex items-center justify-between gap-3">
                          <span className="text-body truncate">{row.name}</span>
                          <span className="text-body-strong tabular-nums">
                            {row.count} <span className="text-meta">({pct}%)</span>
                          </span>
                        </div>
                        <div className="h-1.5 w-full bg-muted rounded-xs overflow-hidden">
                          <div
                            className="h-full bg-foreground rounded-xs transition-[width] duration-500 ease-out"
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* By Group & Status */}
              <div className="rounded-lg border border-border bg-card overflow-hidden">
                <div className="h-10 px-4 border-b border-border bg-background flex items-center justify-between">
                  <span className="text-body-strong">By support group &amp; status</span>
                  <span className="text-meta">Count</span>
                </div>
                <div className="divide-y divide-border-subtle">
                  {data.by_group.map((g) => (
                    <div
                      key={g.name}
                      className="px-4 py-2.5 flex items-center justify-between gap-3"
                    >
                      <span className="text-body truncate">{g.name}</span>
                      <span className="text-body-strong tabular-nums">{g.count}</span>
                    </div>
                  ))}
                </div>
                <div className="h-9 px-4 border-y border-border bg-background flex items-center">
                  <span className="text-meta">By status &amp; priority</span>
                </div>
                <div className="p-4 flex flex-wrap gap-2">
                  {Object.entries(data.by_status).map(([st, cnt]) => (
                    <span
                      key={st}
                      className="inline-flex h-6 items-center gap-1.5 rounded-sm border border-border bg-card px-2 text-[13px] text-foreground tabular-nums"
                    >
                      <span>{STATUS_LABELS[st as TicketStatus] || st}</span>
                      <span className="text-muted-foreground">{cnt}</span>
                    </span>
                  ))}
                  {Object.entries(data.by_priority).map(([pr, cnt]) => (
                    <span
                      key={pr}
                      className="inline-flex h-6 items-center gap-1.5 rounded-sm border border-border bg-muted px-2 text-[13px] text-foreground tabular-nums"
                    >
                      <span>{PRIORITY_LABELS[pr as TicketPriority] || pr}</span>
                      <span className="text-muted-foreground">{cnt}</span>
                    </span>
                  ))}
                </div>
              </div>

              {/* Top Assets */}
              <div className="rounded-lg border border-border bg-card overflow-hidden">
                <div className="h-10 px-4 border-b border-border bg-background flex items-center justify-between">
                  <span className="text-body-strong">Top affected assets</span>
                  <span className="text-meta">Incidents</span>
                </div>
                {data.top_assets.length === 0 ? (
                  <p className="p-4 text-meta-faint">No asset codes recorded in range.</p>
                ) : (
                  <div className="divide-y divide-border-subtle">
                    {data.top_assets.map((item) => (
                      <Link
                        key={item.asset_code}
                        href="/workspace"
                        className="px-4 py-2.5 flex items-center justify-between gap-3 hover:bg-muted/60 transition-colors duration-75"
                      >
                        <span className="text-body font-mono tabular-nums">
                          {item.asset_code}
                        </span>
                        <span className="text-body-strong tabular-nums">{item.count}</span>
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </AppShell>
  );
}

