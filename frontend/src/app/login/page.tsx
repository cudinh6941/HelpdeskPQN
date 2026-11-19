"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { KeyRound, Loader2, Terminal } from "lucide-react";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { isItRole, ROLE_LABELS } from "@/lib/formatters";
import { DemoAccount } from "@/lib/types";
import { useNavigationProgress } from "@/components/NavigationProgress";
import { Button, inputBaseClass } from "@/components/ui/primitives";

export default function LoginPage() {
  const { user, login } = useAuth();
  const router = useRouter();
  const { startNavigation } = useNavigationProgress();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [demoAccounts, setDemoAccounts] = useState<DemoAccount[]>([]);

  useEffect(() => {
    if (user) {
      const target = isItRole(user.role) ? "/workspace" : "/portal";
      startNavigation(target);
      router.replace(target);
    }
  }, [user, router, startNavigation]);

  useEffect(() => {
    api
      .getDemoAccounts()
      .then(setDemoAccounts)
      .catch(() => setDemoAccounts([]));
  }, []);

  const performLogin = async (u: string, p: string) => {
    setError(null);
    setSubmitting(true);
    try {
      const loggedUser = await login(u, p);
      const target = isItRole(loggedUser.role) ? "/workspace" : "/portal";
      startNavigation(target);
      router.replace(target);
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : "Không thể đăng nhập. Kiểm tra lại tên tài khoản và mật khẩu công ty."
      );
    } finally {
      setSubmitting(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void performLogin(username, password);
  };

  return (
    <div className="min-h-dvh bg-background flex items-center justify-center px-4 py-8">
      <div className="w-full max-w-[380px] space-y-4">
        <div className="rounded-lg border border-border bg-card p-5 space-y-4">
          <div className="flex items-center gap-2.5">
            <span className="size-7 rounded-sm bg-primary text-primary-foreground inline-flex items-center justify-center shrink-0">
              <Terminal className="size-4" strokeWidth={1.75} />
            </span>
            <div>
              <h1 className="text-[17px] leading-[22px] font-medium text-foreground">
                Sign in to Helpdesk
              </h1>
              <p className="text-meta">
                Use your corporate LDAP / Active Directory account
              </p>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-3">
            <div className="space-y-1">
              <label className="block text-meta">Corporate username</label>
              <input
                type="text"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="nhanvien or COMPANY\\nhanvien"
                className={inputBaseClass}
              />
            </div>

            <div className="space-y-1">
              <label className="block text-meta">Password</label>
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter domain password"
                className={inputBaseClass}
              />
            </div>

            {error && (
              <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-[13px] text-destructive">
                {error}
              </div>
            )}

            <Button type="submit" disabled={submitting} className="w-full">
              {submitting ? (
                <Loader2 className="size-3.5 animate-spin" strokeWidth={1.5} />
              ) : (
                <KeyRound className="size-3.5" strokeWidth={1.5} />
              )}
              <span>Sign in</span>
            </Button>
          </form>
        </div>

        {demoAccounts.length > 0 && (
          <div className="rounded-lg border border-border bg-card overflow-hidden">
            <div className="h-9 px-4 flex items-center justify-between border-b border-border-subtle bg-background">
              <span className="text-meta">Quick test accounts (local fallback)</span>
              <span className="text-meta-faint font-mono">Password123!</span>
            </div>
            <div className="divide-y divide-border-subtle">
              {demoAccounts.map((acc) => (
                <button
                  key={acc.username}
                  type="button"
                  disabled={submitting}
                  onClick={() => {
                    setUsername(acc.username);
                    setPassword(acc.default_password);
                    void performLogin(acc.username, acc.default_password);
                  }}
                  className="w-full px-4 py-2.5 flex items-center justify-between gap-3 text-left bg-card hover:bg-muted/60 transition-colors duration-75"
                >
                  <div className="min-w-0">
                    <span className="text-body-strong">{acc.full_name}</span>
                    <span className="text-meta ml-2 font-mono">{acc.username}</span>
                  </div>
                  <span className="inline-flex h-6 items-center rounded-sm border border-border bg-card px-2 text-[13px] text-muted-foreground shrink-0">
                    {ROLE_LABELS[acc.role]}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
