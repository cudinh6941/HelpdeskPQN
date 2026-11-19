"use client";

import React from "react";
import { Terminal } from "lucide-react";

import { SkeletonRow } from "@/components/ui/primitives";

export function BrandBootScreen({
  label = "Preparing workspace...",
}: {
  label?: string;
}) {
  return (
    <div className="min-h-dvh flex items-center justify-center bg-background px-4">
      <div className="anim-fade-up flex flex-col items-center gap-3.5">
        <div className="flex items-center gap-2.5">
          <span className="size-8 rounded-sm bg-primary text-primary-foreground inline-flex items-center justify-center">
            <Terminal className="size-4" strokeWidth={1.75} />
          </span>
          <span className="text-[17px] leading-[22px] font-medium text-foreground">
            IT Helpdesk
          </span>
        </div>

        <div className="w-[168px] h-[2px] rounded-full bg-border overflow-hidden">
          <div className="h-full bg-foreground rounded-full anim-boot-bar" />
        </div>

        <span className="text-meta">{label}</span>
      </div>
    </div>
  );
}

export function TopBarSkeleton() {
  return (
    <header className="sticky top-0 z-30 h-11 bg-card border-b border-border px-4 flex items-center justify-between gap-4 shrink-0">
      <div className="flex items-center gap-4 min-w-0">
        <div className="flex items-center gap-2 shrink-0">
          <span className="size-6 rounded-sm bg-primary text-primary-foreground inline-flex items-center justify-center">
            <Terminal className="size-3.5" strokeWidth={1.75} />
          </span>
          <span className="hidden sm:inline text-body-strong">Helpdesk</span>
        </div>

        <span className="h-4 w-px bg-border" aria-hidden />

        <div className="flex items-center gap-1.5">
          <div className="h-7 w-16 rounded-sm skeleton-sheen" />
          <div className="h-7 w-16 rounded-sm skeleton-sheen" />
          <div className="h-7 w-20 rounded-sm skeleton-sheen hidden sm:block" />
        </div>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        <div className="size-7 rounded-sm skeleton-sheen" />
        <div className="size-7 rounded-sm skeleton-sheen" />
        <div className="hidden md:flex items-center gap-2 ml-1">
          <div className="size-6 rounded-full skeleton-sheen" />
          <div className="h-4 w-24 rounded-xs skeleton-sheen" />
        </div>
      </div>
    </header>
  );
}

export function QueuePageSkeleton() {
  return (
    <main className="flex-1 w-full max-w-[1280px] mx-auto px-4 py-4 space-y-3">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center gap-1.5">
          <div className="h-7 w-14 rounded-sm skeleton-sheen" />
          <div className="h-7 w-16 rounded-sm skeleton-sheen" />
          <div className="h-7 w-20 rounded-sm skeleton-sheen" />
          <div className="h-7 w-20 rounded-sm skeleton-sheen" />
        </div>
        <div className="h-8 w-full sm:w-64 rounded-md skeleton-sheen" />
      </div>

      <div className="rounded-lg border border-border bg-card overflow-hidden">
        <div className="h-9 px-4 border-b border-border-subtle bg-background flex items-center gap-2">
          <div className="size-4 rounded-xs skeleton-sheen" />
          <div className="h-4 w-20 rounded-xs skeleton-sheen" />
        </div>
        <SkeletonRow count={5} />
      </div>
    </main>
  );
}

export function TicketDetailSkeleton({
  twoColumn = false,
}: {
  twoColumn?: boolean;
}) {
  return (
    <main className="flex-1 min-h-0">
      <div
        className={
          twoColumn
            ? "h-[calc(100dvh-44px)] grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_300px] overflow-hidden"
            : "h-[calc(100dvh-44px)] grid grid-cols-1 md:grid-cols-[340px_minmax(0,1fr)] xl:grid-cols-[340px_minmax(0,1fr)_300px] overflow-hidden"
        }
      >
        {!twoColumn && (
          <aside className="hidden md:block border-r border-border bg-background overflow-hidden">
            <div className="h-11 px-4 border-b border-border flex items-center justify-between">
              <div className="h-4 w-16 rounded-xs skeleton-sheen" />
              <div className="h-4 w-6 rounded-xs skeleton-sheen" />
            </div>
            <SkeletonRow count={6} compact />
          </aside>
        )}

        <section className="flex flex-col min-w-0 bg-card overflow-hidden">
          <div className="h-11 px-4 border-b border-border flex items-center justify-between gap-3 shrink-0">
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="h-4 w-20 rounded-xs skeleton-sheen" />
              <div className="h-4 w-56 rounded-xs skeleton-sheen" />
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <div className="h-8 w-24 rounded-sm skeleton-sheen" />
              <div className="h-8 w-20 rounded-sm skeleton-sheen" />
            </div>
          </div>

          <div className="flex-1 p-4 space-y-5">
            <div className="max-w-[760px] space-y-4">
              <div className="flex items-center gap-2.5">
                <div className="size-6 rounded-full skeleton-sheen shrink-0" />
                <div className="h-4 w-32 rounded-xs skeleton-sheen" />
                <div className="h-3.5 w-16 rounded-xs skeleton-sheen" />
              </div>
              <div className="pl-8 space-y-2">
                <div className="h-4 w-full rounded-xs skeleton-sheen" />
                <div className="h-4 w-5/6 rounded-xs skeleton-sheen" />
                <div className="h-4 w-2/3 rounded-xs skeleton-sheen" />
              </div>
              <div className="pt-2 rounded-lg border border-border overflow-hidden">
                <SkeletonRow count={2} compact />
              </div>
            </div>
          </div>
        </section>

        <aside
          className={
            twoColumn
              ? "hidden lg:block border-l border-border bg-background p-4 space-y-4"
              : "hidden xl:block border-l border-border bg-background p-4 space-y-4"
          }
        >
          <div className="h-4 w-24 rounded-xs skeleton-sheen" />
          <div className="space-y-3">
            <div className="h-8 w-full rounded-md skeleton-sheen" />
            <div className="h-8 w-full rounded-md skeleton-sheen" />
            <div className="h-8 w-3/4 rounded-md skeleton-sheen" />
            <div className="h-8 w-2/3 rounded-md skeleton-sheen" />
          </div>
        </aside>
      </div>
    </main>
  );
}

export function PortalPageSkeleton() {
  return (
    <main className="flex-1 w-full max-w-[1280px] mx-auto px-4 py-4">
      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_420px] gap-4 items-start">
        <div className="rounded-lg border border-border bg-card p-5 space-y-4">
          <div className="h-5 w-44 rounded-xs skeleton-sheen" />
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {Array.from({ length: 6 }).map((_, idx) => (
              <div key={idx} className="h-9 rounded-md skeleton-sheen" />
            ))}
          </div>
          <div className="h-9 w-full rounded-md skeleton-sheen" />
          <div className="h-28 w-full rounded-md skeleton-sheen" />
          <div className="h-8 w-32 rounded-sm skeleton-sheen" />
        </div>

        <div className="rounded-lg border border-border bg-card overflow-hidden">
          <div className="h-11 px-4 border-b border-border flex items-center justify-between">
            <div className="h-4 w-28 rounded-xs skeleton-sheen" />
            <div className="h-4 w-8 rounded-xs skeleton-sheen" />
          </div>
          <SkeletonRow count={4} compact />
        </div>
      </div>
    </main>
  );
}

export function AnalyticsPageSkeleton() {
  return (
    <main className="flex-1 w-full max-w-[1280px] mx-auto px-4 py-4 space-y-4">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div className="space-y-1.5">
          <div className="h-5 w-56 rounded-xs skeleton-sheen" />
          <div className="h-4 w-80 max-w-full rounded-xs skeleton-sheen" />
        </div>
        <div className="flex items-center gap-2">
          <div className="h-8 w-24 rounded-sm skeleton-sheen" />
          <div className="h-8 w-24 rounded-sm skeleton-sheen" />
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {Array.from({ length: 4 }).map((_, idx) => (
          <div
            key={idx}
            className="rounded-lg border border-border bg-card p-4 space-y-2"
          >
            <div className="h-3.5 w-24 rounded-xs skeleton-sheen" />
            <div className="h-7 w-16 rounded-xs skeleton-sheen" />
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded-lg border border-border bg-card p-4 h-64 space-y-3">
          <div className="h-4 w-32 rounded-xs skeleton-sheen" />
          <div className="h-48 w-full rounded-md skeleton-sheen" />
        </div>
        <div className="rounded-lg border border-border bg-card p-4 h-64 space-y-3">
          <div className="h-4 w-32 rounded-xs skeleton-sheen" />
          <div className="h-48 w-full rounded-md skeleton-sheen" />
        </div>
      </div>
    </main>
  );
}

export function AdminPageSkeleton() {
  return (
    <main className="flex-1 w-full max-w-[1280px] mx-auto px-4 py-4 space-y-4">
      <div className="space-y-1.5">
        <div className="h-5 w-48 rounded-xs skeleton-sheen" />
        <div className="h-4 w-72 max-w-full rounded-xs skeleton-sheen" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded-lg border border-border bg-card p-4 space-y-3">
          <div className="h-4 w-36 rounded-xs skeleton-sheen" />
          <div className="h-9 w-full rounded-md skeleton-sheen" />
          <div className="h-9 w-full rounded-md skeleton-sheen" />
          <div className="h-8 w-28 rounded-sm skeleton-sheen" />
        </div>
        <div className="rounded-lg border border-border bg-card p-4 space-y-3">
          <div className="h-4 w-40 rounded-xs skeleton-sheen" />
          <div className="h-9 w-full rounded-md skeleton-sheen" />
          <div className="h-20 w-full rounded-md skeleton-sheen" />
        </div>
      </div>
    </main>
  );
}

export function KbPageSkeleton() {
  return (
    <main className="flex-1 min-h-0">
      <div className="h-[calc(100dvh-44px)] grid grid-cols-1 md:grid-cols-[360px_minmax(0,1fr)] overflow-hidden">
        <aside className="border-r border-border bg-background p-3 space-y-3">
          <div className="flex items-center justify-between">
            <div className="h-5 w-32 rounded-xs skeleton-sheen" />
            <div className="h-7 w-24 rounded-sm skeleton-sheen" />
          </div>
          <div className="h-8 w-full rounded-md skeleton-sheen" />
          <div className="flex items-center gap-1.5">
            <div className="h-7 w-12 rounded-sm skeleton-sheen" />
            <div className="h-7 w-24 rounded-sm skeleton-sheen" />
            <div className="h-7 w-20 rounded-sm skeleton-sheen" />
          </div>
          <div className="rounded-lg border border-border bg-card overflow-hidden">
            <SkeletonRow count={5} compact />
          </div>
        </aside>

        <section className="hidden md:block bg-card p-6 space-y-4">
          <div className="h-6 w-2/3 rounded-xs skeleton-sheen" />
          <div className="h-4 w-48 rounded-xs skeleton-sheen" />
          <div className="h-24 w-full rounded-md skeleton-sheen" />
          <div className="h-32 w-full rounded-md skeleton-sheen" />
        </section>
      </div>
    </main>
  );
}

export function WorkspaceBootSkeleton({ pathname }: { pathname: string }) {
  return (
    <div className="min-h-dvh flex flex-col bg-background text-foreground">
      <TopBarSkeleton />
      {pathname.startsWith("/workspace/tickets/") ? (
        <TicketDetailSkeleton />
      ) : pathname.startsWith("/portal/tickets/") ? (
        <TicketDetailSkeleton twoColumn />
      ) : pathname.startsWith("/workspace/kb") ? (
        <KbPageSkeleton />
      ) : pathname.startsWith("/workspace/analytics") ? (
        <AnalyticsPageSkeleton />
      ) : pathname.startsWith("/workspace/admin") ? (
        <AdminPageSkeleton />
      ) : pathname.startsWith("/portal") ? (
        <PortalPageSkeleton />
      ) : (
        <QueuePageSkeleton />
      )}
    </div>
  );
}
