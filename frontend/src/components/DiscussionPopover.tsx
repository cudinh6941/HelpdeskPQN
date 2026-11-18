"use client";

import React, { useEffect, useState } from "react";
import {
  Hash,
  MoreHorizontal,
  Paperclip,
  Send,
  SlidersHorizontal,
  Smile,
  X,
} from "lucide-react";

import { formatRelativeTime } from "@/lib/formatters";
import { Avatar, Button } from "@/components/ui/primitives";

export interface DiscussionMessage {
  id: string;
  author: string;
  body: string;
  createdAt: string;
}

interface DiscussionPopoverProps {
  open: boolean;
  onClose: () => void;
  channelName: string;
  startedAt?: string | null;
  messages: DiscussionMessage[];
  onSendMessage: (text: string) => Promise<void>;
}

export function DiscussionPopover({
  open,
  onClose,
  channelName,
  startedAt,
  messages,
  onSendMessage,
}: DiscussionPopoverProps) {
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  const submitMessage = async () => {
    const text = draft.trim();
    if (!text || sending) return;
    setSending(true);
    try {
      await onSendMessage(text);
      setDraft("");
    } finally {
      setSending(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`Discussion in ${channelName}`}
      onClick={onClose}
      className="anim-scrim fixed inset-0 z-50 bg-[var(--scrim)] backdrop-blur-[2px] flex items-center justify-center p-4"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="anim-popover w-full max-w-[400px] rounded-xl border border-border bg-card shadow-popover overflow-hidden"
      >
        {/* Header 56px */}
        <div className="h-14 px-4 py-2.5 border-b border-border-subtle flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex items-center gap-1 text-body-strong truncate">
              <span>Discussion in</span>
              <Hash className="size-3.5 text-muted-foreground shrink-0" strokeWidth={1.75} />
              <span className="truncate">{channelName.replace(/^#/, "")}</span>
            </div>
            <p className="text-meta-faint truncate">
              Started {formatRelativeTime(startedAt)}
            </p>
          </div>

          <div className="flex items-center gap-0.5 shrink-0">
            <Button variant="icon" type="button" aria-label="More options">
              <MoreHorizontal className="size-4" strokeWidth={1.5} />
            </Button>
            <Button variant="icon" type="button" onClick={onClose} aria-label="Close discussion">
              <X className="size-4" strokeWidth={1.5} />
            </Button>
          </div>
        </div>

        {/* Messages Stream (no bubbles) */}
        <div className="max-h-[320px] overflow-y-auto p-4 space-y-5">
          {messages.length === 0 ? (
            <p className="text-meta-faint">No internal discussion messages yet.</p>
          ) : (
            messages.map((m) => (
              <div key={m.id} className="anim-fade-up">
                <div className="flex items-center gap-2">
                  <Avatar name={m.author} />
                  <span className="text-body-strong">{m.author}</span>
                  <span className="text-meta-faint">{formatRelativeTime(m.createdAt)}</span>
                </div>
                <p className="pl-8 mt-0.5 text-body whitespace-pre-wrap">{m.body}</p>
              </div>
            ))
          )}
        </div>

        {/* Bottom Composer */}
        <div className="p-4 border-t border-border-subtle">
          <textarea
            rows={2}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void submitMessage();
              }
            }}
            placeholder="Add a message"
            className="w-full resize-none bg-transparent text-body placeholder:text-faint focus:outline-none"
          />

          <div className="flex items-center justify-between pt-3">
            <div className="flex items-center gap-3 text-faint">
              <button
                type="button"
                className="hover:text-foreground transition-colors duration-75"
                title="Attach file"
              >
                <Paperclip className="size-4" strokeWidth={1.5} />
              </button>
              <button
                type="button"
                className="hover:text-foreground transition-colors duration-75"
                title="Emoji"
              >
                <Smile className="size-4" strokeWidth={1.5} />
              </button>
              <button
                type="button"
                className="hover:text-foreground transition-colors duration-75"
                title="Formatting"
              >
                <SlidersHorizontal className="size-4" strokeWidth={1.5} />
              </button>
            </div>

            <Button
              type="button"
              variant="primary"
              disabled={!draft.trim() || sending}
              onClick={() => void submitMessage()}
            >
              <Send className="size-3.5" strokeWidth={1.5} />
              <span>Send</span>
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
