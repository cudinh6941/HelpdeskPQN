"use client";

import React, { useState } from "react";
import { BookOpen, Check, Copy, FileText, Lock, MessageSquare, X } from "lucide-react";

import { Button } from "@/components/ui/primitives";
import { buildAttachmentUrl } from "@/lib/api";
import { KbArticleBrief } from "@/lib/types";

export function CommentKbCard({
  kb,
  showUserActions = false,
  actionBusy = false,
  onUserSolved,
  onUserNeedHelp,
}: {
  kb: KbArticleBrief;
  showUserActions?: boolean;
  actionBusy?: boolean;
  onUserSolved?: () => void;
  onUserNeedHelp?: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const [lightbox, setLightbox] = useState<{ url: string; name: string } | null>(null);

  const images = (kb.attachments || []).filter((a) =>
    a.content_type.startsWith("image/")
  );
  const files = (kb.attachments || []).filter(
    (a) => !a.content_type.startsWith("image/")
  );

  const handleCopySteps = async () => {
    try {
      const text = [
        kb.title,
        ...kb.steps.map((s, idx) => `${idx + 1}. ${s}`),
      ].join("\n");
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // ignore clipboard restrictions
    }
  };

  return (
    <>
      <div className="ml-8 mt-2 rounded-md border border-border bg-background overflow-hidden">
        <div className="px-3 py-2 border-b border-border-subtle flex items-center justify-between gap-2 bg-card">
          <div className="flex items-center gap-2 min-w-0">
            <BookOpen className="size-3.5 text-[var(--action-reply)] shrink-0" strokeWidth={1.5} />
            <span className="text-[13px] font-medium text-foreground truncate">
              {kb.title}
            </span>
            {kb.visibility === "INTERNAL" && (
              <span className="inline-flex items-center gap-1 rounded-xs border border-note-border bg-note px-1.5 py-0.5 text-[11px] font-medium text-note-ink shrink-0">
                <Lock className="size-2.5" strokeWidth={1.75} />
                <span>IT Runbook</span>
              </span>
            )}
          </div>

          {kb.steps.length > 0 && (
            <button
              type="button"
              onClick={() => void handleCopySteps()}
              className="inline-flex items-center gap-1 text-[12px] text-muted-foreground hover:text-foreground shrink-0"
            >
              {copied ? (
                <Check className="size-3" strokeWidth={1.5} />
              ) : (
                <Copy className="size-3" strokeWidth={1.5} />
              )}
              <span>{copied ? "Copied" : "Copy"}</span>
            </button>
          )}
        </div>

        <div className="p-3 space-y-2.5">
          {kb.steps.length > 0 && (
            <ol className="space-y-1.5">
              {kb.steps.map((step, idx) => (
                <li key={idx} className="flex items-start gap-2 text-[13px] leading-[19px] text-foreground">
                  <span className="size-4 rounded-xs bg-muted text-muted-foreground text-[11px] font-medium inline-flex items-center justify-center shrink-0 mt-0.5 tabular-nums">
                    {idx + 1}
                  </span>
                  <span className="whitespace-pre-wrap">{step}</span>
                </li>
              ))}
            </ol>
          )}

          {kb.notes && (
            <pre className="rounded-sm border border-border bg-card px-2.5 py-2 font-mono text-[12px] leading-4 text-foreground overflow-x-auto whitespace-pre-wrap">
              {kb.notes}
            </pre>
          )}

          {images.length > 0 && (
            <div className="flex flex-wrap gap-2 pt-0.5">
              {images.map((att) => {
                const url = buildAttachmentUrl(att.download_url);
                return (
                  <button
                    key={att.id}
                    type="button"
                    onClick={() => setLightbox({ url, name: att.file_name })}
                    className="rounded-sm border border-border bg-card overflow-hidden hover:border-foreground/40 transition-colors duration-75"
                    title={`Click to zoom ${att.file_name}`}
                  >
                    <img
                      src={url}
                      alt={att.file_name}
                      className="h-24 w-auto object-cover"
                    />
                  </button>
                );
              })}
            </div>
          )}

          {files.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {files.map((att) => (
                <a
                  key={att.id}
                  href={buildAttachmentUrl(att.download_url)}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-sm border border-border bg-card px-2.5 py-1 text-[12px] text-foreground hover:bg-muted"
                >
                  <FileText className="size-3.5 text-muted-foreground" strokeWidth={1.5} />
                  <span>{att.file_name}</span>
                </a>
              ))}
            </div>
          )}
        </div>

        {showUserActions && (
          <div className="px-3 py-2.5 border-t border-border-subtle bg-card flex flex-wrap items-center justify-between gap-2">
            <span className="text-[12px] text-muted-foreground">
              Bạn làm theo hướng dẫn trên đã xử lý được chưa?
            </span>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={actionBusy}
                onClick={onUserNeedHelp}
              >
                <MessageSquare className="size-3.5" strokeWidth={1.5} />
                <span>Chưa được, cần IT hỗ trợ</span>
              </Button>
              <Button
                type="button"
                size="sm"
                variant="primary"
                disabled={actionBusy}
                onClick={onUserSolved}
              >
                <Check className="size-3.5" strokeWidth={1.75} />
                <span>Đã xử lý xong (Đóng ticket)</span>
              </Button>
            </div>
          </div>
        )}
      </div>

      {lightbox && (
        <div
          role="dialog"
          aria-modal="true"
          onClick={() => setLightbox(null)}
          className="anim-scrim fixed inset-0 z-50 bg-[var(--scrim)] backdrop-blur-[2px] flex items-center justify-center p-4"
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="anim-popover relative max-w-4xl max-h-[88dvh] rounded-lg border border-border bg-card shadow-popover overflow-hidden flex flex-col"
          >
            <div className="h-10 px-4 border-b border-border flex items-center justify-between gap-4">
              <span className="text-meta truncate">{lightbox.name}</span>
              <Button
                type="button"
                variant="icon"
                onClick={() => setLightbox(null)}
                aria-label="Close image preview"
              >
                <X className="size-4" strokeWidth={1.5} />
              </Button>
            </div>
            <div className="p-3 overflow-auto bg-background flex items-center justify-center">
              <img
                src={lightbox.url}
                alt={lightbox.name}
                className="max-h-[76dvh] w-auto object-contain rounded-sm"
              />
            </div>
          </div>
        </div>
      )}
    </>
  );
}
