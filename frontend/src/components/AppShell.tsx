"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  BarChart3,
  Bell,
  BellRing,
  BookOpen,
  CheckCheck,
  ChevronDown,
  Inbox,
  Loader2,
  LogOut,
  Plus,
  Settings,
  Terminal,
  Volume2,
  VolumeX,
  X,
} from "lucide-react";

import { WorkspaceBootSkeleton } from "@/components/LoadingSkeletons";
import { useNavigationProgress } from "@/components/NavigationProgress";

import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useAuth } from "@/lib/auth-context";
import { formatRelativeTime, isItRole, ROLE_LABELS } from "@/lib/formatters";
import {
  isSoundMuted,
  playNotificationChime,
  setSoundMuted,
  triggerDesktopNotification,
} from "@/lib/notifications";
import { NotificationItem } from "@/lib/types";
import { useRealtime } from "@/lib/use-realtime";
import { Avatar, Button, inputBaseClass } from "@/components/ui/primitives";

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
  const { user, loading, logout, refreshUser } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const { isNavigating, pendingPath, startNavigation } = useNavigationProgress();

  const [muted, setMuted] = useState(false);
  const [notifPerm, setNotifPerm] = useState<NotificationPermission>("default");
  const [toast, setToast] = useState<ToastItem | null>(null);
  const toastTimerRef = useRef<number | null>(null);

  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [notifOpen, setNotifOpen] = useState(false);
  const [notifBusy, setNotifBusy] = useState(false);

  const [profileOpen, setProfileOpen] = useState(false);
  const [tgInput, setTgInput] = useState("");
  const [zaloInput, setZaloInput] = useState("");
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileMsg, setProfileMsg] = useState<string | null>(null);

  const notifBoxRef = useRef<HTMLDivElement | null>(null);
  const profileBoxRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setMuted(isSoundMuted());
    if (typeof window !== "undefined" && "Notification" in window) {
      setNotifPerm(Notification.permission);
    }
  }, []);

  useEffect(() => {
    if (user) {
      setTgInput(user.telegram_chat_id || "");
      setZaloInput(user.zalo_user_id || "");
    }
  }, [user]);

  useEffect(() => {
    if (!loading && !user) {
      startNavigation("/login");
      router.replace("/login");
    }
  }, [loading, user, router, startNavigation]);

  const loadNotifications = useCallback(async () => {
    if (!user) return;
    try {
      const res = await api.listNotifications({ limit: 25 });
      setNotifications(res.items);
      setUnreadCount(res.unread_count);
    } catch {
      // ignore transient fetch errors
    }
  }, [user]);

  useEffect(() => {
    if (user) {
      void loadNotifications();
    }
  }, [user, loadNotifications]);

  useEffect(() => {
    const onPointerDown = (e: MouseEvent) => {
      const target = e.target as Node;
      if (notifBoxRef.current && !notifBoxRef.current.contains(target)) {
        setNotifOpen(false);
      }
      if (profileBoxRef.current && !profileBoxRef.current.contains(target)) {
        setProfileOpen(false);
      }
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setNotifOpen(false);
        setProfileOpen(false);
      }
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, []);

  useRealtime((evt) => {
    if (!user) return;
    void loadNotifications();

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
    triggerDesktopNotification(`Helpdesk · ${code}`, summary, href, (target) => {
      startNavigation(target);
      router.push(target);
    });

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

  const handleNotificationClick = async (item: NotificationItem) => {
    setNotifOpen(false);
    if (!item.is_read) {
      setNotifications((prev) =>
        prev.map((n) => (n.id === item.id ? { ...n, is_read: true } : n))
      );
      setUnreadCount((prev) => Math.max(0, prev - 1));
      try {
        await api.markNotificationRead(item.id);
      } catch {
        // ignore transient error
      }
    }
    startNavigation(item.link_url);
    router.push(item.link_url);
  };

  const handleMarkAllRead = async () => {
    setNotifBusy(true);
    try {
      await api.markAllNotificationsRead();
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      setUnreadCount(0);
    } finally {
      setNotifBusy(false);
    }
  };

  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setProfileSaving(true);
    setProfileMsg(null);
    try {
      await api.updateMyProfile({
        telegram_chat_id: tgInput.trim() || null,
        zalo_user_id: zaloInput.trim() || null,
      });
      await refreshUser();
      setProfileMsg("Saved notification channels.");
    } catch (err: unknown) {
      setProfileMsg(err instanceof Error ? err.message : "Could not save profile.");
    } finally {
      setProfileSaving(false);
    }
  };

  if (loading || !user) {
    return <WorkspaceBootSkeleton pathname={pathname} />;
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
      href: "/workspace/kb",
      label: "Knowledge",
      icon: BookOpen,
      visible: hasItAccess,
      active: pathname.startsWith("/workspace/kb"),
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
              const isPendingTarget =
                isNavigating && !item.active && pendingPath === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "inline-flex items-center gap-1.5 h-7 px-2.5 rounded-sm text-[13px] font-medium transition-[background-color,color,transform] duration-100 active:translate-y-[0.5px] whitespace-nowrap",
                    item.active
                      ? "bg-muted text-foreground"
                      : isPendingTarget
                      ? "bg-muted/70 text-foreground"
                      : "text-muted-foreground hover:bg-muted/60 hover:text-foreground"
                  )}
                >
                  {isPendingTarget ? (
                    <Loader2 className="size-3.5 animate-spin text-ring" strokeWidth={1.75} />
                  ) : (
                    <Icon className="size-3.5" strokeWidth={1.5} />
                  )}
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

          {/* Notification Inbox */}
          <div ref={notifBoxRef} className="relative">
            <Button
              variant="icon"
              type="button"
              onClick={() => {
                const next = !notifOpen;
                setNotifOpen(next);
                setProfileOpen(false);
                if (next) void loadNotifications();
              }}
              title="Notifications"
              aria-label="Open notifications"
              className="relative"
            >
              {notifPerm === "granted" ? (
                <BellRing className="size-4 text-foreground" strokeWidth={1.5} />
              ) : (
                <Bell className="size-4" strokeWidth={1.5} />
              )}
              {unreadCount > 0 && (
                <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 rounded-full bg-destructive text-destructive-foreground text-[10px] font-semibold leading-4 text-center tabular-nums">
                  {unreadCount > 99 ? "99+" : unreadCount}
                </span>
              )}
            </Button>

            {notifOpen && (
              <div className="anim-fade-up absolute right-0 mt-1.5 w-[340px] max-w-[92vw] rounded-lg border border-border bg-card shadow-popover z-50 overflow-hidden">
                <div className="px-3 py-2 border-b border-border bg-background flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="text-[13px] font-medium text-foreground">
                      Notifications
                    </span>
                    {unreadCount > 0 && (
                      <span className="text-[11px] font-medium px-1.5 py-0.5 rounded-sm bg-destructive/10 text-destructive tabular-nums">
                        {unreadCount} unread
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-1.5">
                    {unreadCount > 0 && (
                      <button
                        type="button"
                        disabled={notifBusy}
                        onClick={() => void handleMarkAllRead()}
                        className="inline-flex items-center gap-1 text-[12px] text-muted-foreground hover:text-foreground"
                      >
                        <CheckCheck className="size-3.5" strokeWidth={1.5} />
                        <span>Mark all read</span>
                      </button>
                    )}
                  </div>
                </div>

                {notifPerm !== "granted" && (
                  <div className="px-3 py-2 border-b border-border-subtle bg-muted/40 flex items-center justify-between gap-2 text-[12px]">
                    <span className="text-muted-foreground">Desktop popups disabled</span>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => void handleRequestNotif()}
                    >
                      Enable
                    </Button>
                  </div>
                )}

                <div className="max-h-[360px] overflow-y-auto divide-y divide-border-subtle">
                  {notifications.length === 0 ? (
                    <p className="px-3 py-6 text-center text-meta">
                      No notifications yet.
                    </p>
                  ) : (
                    notifications.map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => void handleNotificationClick(item)}
                        className={cn(
                          "w-full text-left px-3 py-2.5 flex items-start gap-2.5 hover:bg-muted/60 transition-colors duration-75",
                          !item.is_read && "bg-muted/30"
                        )}
                      >
                        <span
                          className={cn(
                            "mt-1.5 size-2 rounded-full shrink-0",
                            item.is_read ? "bg-transparent" : "bg-ring"
                          )}
                        />
                        <div className="min-w-0 flex-1 space-y-0.5">
                          <p className="text-[13px] font-medium text-foreground truncate">
                            {item.title}
                          </p>
                          <p className="text-[12px] text-muted-foreground line-clamp-2">
                            {item.body}
                          </p>
                          <p className="text-[11px] text-faint tabular-nums">
                            {formatRelativeTime(item.created_at)}
                          </p>
                        </div>
                      </button>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>

          {/* User Profile & Notification Channels */}
          <div ref={profileBoxRef} className="relative">
            <button
              type="button"
              onClick={() => {
                setProfileOpen((prev) => !prev);
                setNotifOpen(false);
                setProfileMsg(null);
              }}
              className="hidden md:inline-flex items-center gap-2 h-7 px-2 rounded-sm text-[13px] ml-1 hover:bg-muted transition-colors duration-75"
              title="Profile & notification channels"
            >
              <Avatar name={user.full_name} />
              <span className="font-medium text-foreground">{user.full_name}</span>
              <span className="text-muted-foreground">/</span>
              <span className="text-muted-foreground">{ROLE_LABELS[user.role]}</span>
              <ChevronDown className="size-3.5 text-muted-foreground" strokeWidth={1.5} />
            </button>

            {profileOpen && (
              <div className="anim-fade-up absolute right-0 mt-1.5 w-[310px] rounded-lg border border-border bg-card shadow-popover z-50 overflow-hidden">
                <div className="px-3.5 py-2.5 border-b border-border bg-background space-y-0.5">
                  <p className="text-[13px] font-medium text-foreground">
                    {user.full_name}{" "}
                    <span className="text-meta font-mono">@{user.username}</span>
                  </p>
                  <p className="text-meta truncate">{user.email}</p>
                  <p className="text-meta-faint">
                    {ROLE_LABELS[user.role]}
                    {user.department ? ` · ${user.department.name}` : ""}
                  </p>
                </div>

                <form onSubmit={handleSaveProfile} className="p-3.5 space-y-2.5">
                  <div className="space-y-1">
                    <label className="block text-meta">Telegram Chat ID</label>
                    <input
                      type="text"
                      value={tgInput}
                      onChange={(e) => setTgInput(e.target.value)}
                      placeholder="e.g. 123456789"
                      className={cn(inputBaseClass, "h-8 text-[13px] font-mono")}
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="block text-meta">Zalo User ID</label>
                    <input
                      type="text"
                      value={zaloInput}
                      onChange={(e) => setZaloInput(e.target.value)}
                      placeholder="e.g. zalo_uid_..."
                      className={cn(inputBaseClass, "h-8 text-[13px] font-mono")}
                    />
                  </div>
                  {profileMsg && (
                    <p className="text-[12px] text-foreground">{profileMsg}</p>
                  )}
                  <div className="flex justify-end pt-1">
                    <Button type="submit" size="sm" disabled={profileSaving}>
                      {profileSaving ? "Saving..." : "Save channels"}
                    </Button>
                  </div>
                </form>
              </div>
            )}
          </div>

          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              startNavigation("/login");
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
              startNavigation(target);
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
