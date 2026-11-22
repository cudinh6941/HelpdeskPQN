"use client";

import React from "react";
import { Download, FileText } from "lucide-react";

import { buildAttachmentUrl } from "@/lib/api";
import { cn } from "@/lib/cn";
import { Attachment } from "@/lib/types";

function formatFileSize(bytes: number): string {
  if (bytes >= 1024 * 1024) {
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }
  return `${Math.max(0.1, bytes / 1024).toFixed(1)} KB`;
}

export function AttachmentList({
  attachments,
  noteStyle = false,
  className,
}: {
  attachments: Attachment[];
  noteStyle?: boolean;
  className?: string;
}) {
  if (!attachments || attachments.length === 0) return null;

  return (
    <div className={cn("pl-8 mt-2 flex flex-wrap gap-2", className)}>
      {attachments.map((att) => {
        const isImage = att.content_type.startsWith("image/");
        const url = buildAttachmentUrl(att.download_url);

        if (isImage) {
          return (
            <a
              key={att.id}
              href={url}
              target="_blank"
              rel="noreferrer"
              className={cn(
                "rounded-sm border overflow-hidden hover:border-foreground/40 transition-colors",
                noteStyle ? "border-note-border" : "border-border"
              )}
            >
              <img
                src={url}
                alt={att.file_name}
                className="h-24 w-auto object-cover"
              />
            </a>
          );
        }

        return (
          <a
            key={att.id}
            href={url}
            target="_blank"
            rel="noreferrer"
            className={cn(
              "inline-flex items-center gap-2 rounded-sm border bg-card px-2.5 py-1.5 text-[13px] text-foreground hover:bg-muted/60 hover:border-foreground/40 transition-colors max-w-[260px]",
              noteStyle ? "border-note-border" : "border-border"
            )}
            title={`${att.file_name} (${formatFileSize(att.size_bytes)})`}
          >
            <FileText className="size-4 text-muted-foreground shrink-0" strokeWidth={1.5} />
            <span className="truncate font-medium">{att.file_name}</span>
            <span className="text-[11px] text-faint tabular-nums shrink-0">
              {formatFileSize(att.size_bytes)}
            </span>
            <Download className="size-3.5 text-muted-foreground shrink-0" strokeWidth={1.5} />
          </a>
        );
      })}
    </div>
  );
}

