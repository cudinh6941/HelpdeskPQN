"use client";

import { useEffect, useRef } from "react";
import { api, API_BASE, getStoredToken } from "./api";

export interface RealtimeEvent {
  type:
    | "TICKET_CREATED"
    | "TICKET_UPDATED"
    | "COMMENT_ADDED"
    | "ULTRAVIEW_REQUESTED"
    | "ULTRAVIEW_PROVIDED";
  ticket_id: string;
  is_internal: boolean;
  payload?: Record<string, unknown>;
}

function buildWsUrl(token: string): string {
  let wsBase: string;
  if (!API_BASE) {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    wsBase = `${proto}//${window.location.host}`;
  } else {
    wsBase = API_BASE.replace(/^http/i, "ws");
  }
  return `${wsBase}/api/v1/ws?token=${encodeURIComponent(token)}`;
}

export function useRealtime(onEvent: (event: RealtimeEvent) => void): void {
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  useEffect(() => {
    let active = true;
    let ws: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let pingTimer: number | null = null;

    const cleanupTimers = () => {
      if (pingTimer !== null) {
        window.clearInterval(pingTimer);
        pingTimer = null;
      }
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
    };

    const connect = async () => {
      if (!active) return;
      const storedToken = getStoredToken();
      if (!storedToken) return;

      let wsToken = storedToken;
      try {
        const scoped = await api.getScopedToken("ws");
        if (!active) return;
        wsToken = scoped.token;
      } catch {
        // fallback to stored token if transient error occurs
      }

      if (!active) return;
      try {
        ws = new WebSocket(buildWsUrl(wsToken));
      } catch {
        reconnectTimer = window.setTimeout(() => void connect(), 2500);
        return;
      }

      ws.onopen = () => {
        pingTimer = window.setInterval(() => {
          if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send("ping");
          }
        }, 25000);
      };

      ws.onmessage = (evt) => {
        if (evt.data === "pong") return;
        try {
          const parsed = JSON.parse(evt.data) as RealtimeEvent;
          if (parsed && parsed.type) {
            onEventRef.current(parsed);
          }
        } catch {
          // ignore non-JSON frames
        }
      };

      ws.onclose = () => {
        cleanupTimers();
        if (active) {
          reconnectTimer = window.setTimeout(() => void connect(), 2000);
        }
      };

      ws.onerror = () => {
        ws?.close();
      };
    };

    void connect();

    return () => {
      active = false;
      cleanupTimers();
      if (ws) {
        ws.onclose = null;
        ws.close();
      }
    };
  }, []);
}
