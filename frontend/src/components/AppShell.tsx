"use client";

import React, { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  BarChart3,
  Bell,
  BellRing,
  Inbox,
  LogOut,
  Plus,
  Settings,
  Terminal,
  Volume2,
  VolumeX,
  X,
} from "lucide-react";

import { cn } from "@/lib/cn";
import { useAuth } from "@/lib/auth-context";
import { isItRole, ROLE_LABELS } from "@/lib/formatters";
import {
  isSoundMuted,
  playNotificationChime,
  setSoundMuted,
  triggerDesktopNotification,
} from "@/lib/notifications";
import { useRealtime } from "@/lib/use-realtime";
import { Avatar, Button } from "@/components/ui/primitives";

interface ToastItem {
  id: number;
  text: string;
  href: string;
}

export function AppShell({
  children,
  fullBleed = false,
}: {
  children: React.ReactNode;
  fullBleed?: boolean;
}) {
  const { user, loading, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  const [muted, setMuted] = useState(false);
  const [notifPerm, setNotifPerm] = useState<NotificationPermission>("default");
  const [toast, setToast] = useState<ToastItem | null>(null);
  const toastTimerRef = useRef<number | null>(null);

  useEffect(() => {
    setMuted(isSoundMuted());
    if (typeof window !== "undefined" && "Notification" in window) {
      setNotifPerm(Notification.permission);
    }
  }, []);

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [loading, user, router]);

  useRealtime((evt) => {
    if (!user) return;
    const payload = (evt.payload || {}) as Record<string, string>;
    if (payload.actor_id && payload.actor_id === user.id) return;

    const code = payload.ticket_code || "Ticket";
    const summary = payload.summary || `${code} updated`;
    const href = isItRole(user.role)
      ? `/workspace/tickets/${evt.ticket_id}`
      : `/portal/tickets/${evt.ticket_id}`;

    const urgent =
      payload.priority === "CRITICAL" ||
      payload.priority === "HIGH" ||
      evt.type === "ULTRAVIEW_PROVIDED" ||
      evt.type === "ULTRAVIEW_REQUESTED";

    playNotificationChime(urgent);
    triggerDesktopNotification(`Helpdesk · ${code}`, summary, href, (target) =>
      router.push(target)
    );

    setToast({ id: Date.now(), text: summary, href });
    if (toastTimerRef.current !== null) {
      window.clearTimeout(toastTimerRef.current);
    }
    toastTimerRef.current = window.setTimeout(() => {
      setToast(null);
    }, 4500);
  });

  const handleToggleSound = () => {
    const next = !muted;
    setMuted(next);
    setSoundMuted(next);
    if (!next) playNotificationChime(false);
  };

  const handleRequestNotif = async () => {
    if (typeof window === "undefined" || !("Notification" in window)) return;
    const perm = await Notification.requestPermission();
    setNotifPerm(perm);
    if (perm === "granted") {
      playNotificationChime(false);
      new Notification("IT Helpdesk", {
        body: "Desktop notifications enabled for new tickets and replies.",
      });
    }
  };

  if (loading || !user) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <span className="text-meta-faint">Loading workspace...</span>
      </div>
    );
  }

  const hasItAccess = isItRole(user.role);
  const hasLeadOrAdmin = user.role === "IT_LEAD" || user.role === "SYS_ADMIN";

  const navItems = [
    {
      href: "/workspace",
      label: "Queue",
      icon: Inbox,
      visible: hasItAccess,
      active: pathname === "/workspace" || pathname.startsWith("/workspace/tickets"),
    },
    {
      href: "/portal",
      label: "Portal",
      icon: Plus,
      visible: true,
      active: pathname.startsWith("/portal"),
    },
    {
      href: "/workspace/analytics",
      label: "Analytics",
      icon: BarChart3,
      visible: hasItAccess,
      active: pathname.startsWith("/workspace/analytics"),
    },
    {
      href: "/workspace/admin",
      label: "Settings",
      icon: Settings,
      visible: hasLeadOrAdmin,
      active: pathname.startsWith("/workspace/admin"),
    },
  ].filter((item) => item.visible);

  return (
    <div className="min-h-dvh flex flex-col bg-background text-foreground">
      <header className="sticky top-0 z-30 h-11 bg-card border-b border-border px-4 flex items-center justify-between gap-4 shrink-0 relative">
        <span
          key={pathname}
          aria-hidden
          className="anim-topbar-progress pointer-events-none absolute left-0 right-0 bottom-0 h-[1.5px] bg-foreground"
        />
        <div className="flex items-center gap-4 min-w-0">
          <Link
            href={hasItAccess ? "/workspace" : "/portal"}
            className="flex items-center gap-2 text-body-strong shrink-0"
          >
            <span className="size-6 rounded-sm bg-primary text-primary-foreground inline-flex items-center justify-center">
              <Terminal className="size-3.5" strokeWidth={1.75} />
            </span>
            <span className="hidden sm:inline">Helpdesk</span>
          </Link>

          <span className="h-4 w-px bg-border" aria-hidden />

          <nav className="flex items-center gap-1 overflow-x-auto">
            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "inline-flex items-center gap-1.5 h-7 px-2.5 rounded-sm text-[13px] font-medium transition-[background-color,color,transform] duration-100 active:translate-y-[0.5px] whitespace-nowrap",
                    item.active
                      ? "bg-muted text-foreground"
                      : "text-muted-foreground hover:bg-muted/60 hover:text-foreground"
                  )}
                >
                  <Icon className="size-3.5" strokeWidth={1.5} />
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </nav>
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          <Button
            variant="icon"
            type="button"
            onClick={handleToggleSound}
            title={muted ? "Sound muted (click to enable)" : "Notification sound on"}
            aria-label="Toggle notification sound"
          >
            {muted ? (
              <VolumeX className="size-4" strokeWidth={1.5} />
            ) : (
              <Volume2 className="size-4" strokeWidth={1.5} />
            )}
          </Button>

          <Button
            variant="icon"
            type="button"
            onClick={() => void handleRequestNotif()}
            title={
              notifPerm === "granted"
                ? "Desktop notifications enabled"
                : "Enable Windows desktop notifications"
            }
            aria-label="Desktop notification settings"
          >
            {notifPerm === "granted" ? (
              <BellRing className="size-4 text-foreground" strokeWidth={1.5} />
            ) : (
              <Bell className="size-4" strokeWidth={1.5} />
            )}
          </Button>

          <div className="hidden md:flex items-center gap-2 text-[13px] ml-1.5">
            <Avatar name={user.full_name} />
            <span className="font-medium text-foreground">{user.full_name}</span>
            <span className="text-muted-foreground">/</span>
            <span className="text-muted-foreground">{ROLE_LABELS[user.role]}</span>
          </div>

          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              logout();
              router.push("/login");
            }}
            title="Sign out"
          >
            <LogOut className="size-3.5" strokeWidth={1.5} />
            <span className="hidden sm:inline">Sign out</span>
          </Button>
        </div>
      </header>

      <main className={fullBleed ? "flex-1 min-h-0" : "flex-1 w-full max-w-[1280px] mx-auto px-4 py-4"}>
        {children}
      </main>

      {/* 1-Line In-App Toast (§14.5) */}
      {toast && (
        <div
          key={toast.id}
          role="status"
          className="anim-fade-up fixed bottom-4 right-4 z-50 max-w-[420px] rounded-md border border-border bg-card px-3.5 py-2 shadow-popover flex items-center gap-3 text-[13px] text-foreground"
        >
          <button
            type="button"
            onClick={() => {
              const target = toast.href;
              setToast(null);
              router.push(target);
            }}
            className="truncate text-left hover:underline"
          >
            {toast.text}
          </button>
          <button
            type="button"
            onClick={() => setToast(null)}
            className="text-faint hover:text-foreground shrink-0"
            aria-label="Dismiss notification"
          >
            <X className="size-3.5" strokeWidth={1.5} />
          </button>
        </div>
      )}
    </div>
  );
}
