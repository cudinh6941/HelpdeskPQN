"use client";

import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, getStoredToken, setMediaToken, setStoredToken } from "./api";
import { User } from "./types";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<User>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const syncMediaToken = useCallback(async () => {
    try {
      const scoped = await api.getScopedToken("media");
      setMediaToken(scoped.token);
    } catch {
      setMediaToken(null);
    }
  }, []);

  const refreshUser = useCallback(async () => {
    const token = getStoredToken();
    if (!token) {
      setMediaToken(null);
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const me = await api.getMe();
      await syncMediaToken();
      setUser(me);
    } catch {
      setStoredToken(null);
      setMediaToken(null);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, [syncMediaToken]);

  useEffect(() => {
    void refreshUser();
  }, [refreshUser]);

  useEffect(() => {
    if (!user) return;
    const intervalId = window.setInterval(() => {
      void syncMediaToken();
    }, 4 * 60 * 1000);
    return () => window.clearInterval(intervalId);
  }, [user, syncMediaToken]);

  const login = useCallback(
    async (username: string, password: string) => {
      const res = await api.login(username, password);
      setStoredToken(res.access_token);
      await syncMediaToken();
      setUser(res.user);
      return res.user;
    },
    [syncMediaToken]
  );

  const logout = useCallback(() => {
    setStoredToken(null);
    setMediaToken(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return ctx;
}
