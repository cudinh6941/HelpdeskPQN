"use client";

import React, {
  forwardRef,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import { ClipboardPaste, FileImage, Loader2, Paperclip, X } from "lucide-react";

import { api, buildAttachmentUrl } from "@/lib/api";
import { Attachment } from "@/lib/types";
import { Button } from "@/components/ui/primitives";

export interface PasteUploaderHandle {
  uploadFiles: (files: File[]) => Promise<void>;
  clear: () => void;
}

interface Props {
  ticketId?: string;
  kbArticleId?: string;
  attachments: Attachment[];
  onChange: (next: Attachment[]) => void;
  compact?: boolean;
}

export const PasteImageUploader = forwardRef<PasteUploaderHandle, Props>(
  function PasteImageUploader({ ticketId, kbArticleId, attachments, onChange, compact = false }, ref) {
    const [uploading, setUploading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const inputRef = useRef<HTMLInputElement | null>(null);

    const uploadFiles = async (files: File[]) => {
      if (!files.length) return;
      setError(null);
      setUploading(true);
      try {
        const uploaded: Attachment[] = [];
        for (const file of files) {
          const name =
            file.name && file.name !== "image.png"
              ? file.name
              : `pasted-${Date.now()}.png`;
          const att = await api.uploadAttachment(file, name, ticketId, kbArticleId);
          uploaded.push(att);
        }
        onChange([...attachments, ...uploaded]);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : "Upload file thất bại");
      } finally {
        setUploading(false);
      }
    };

    useImperativeHandle(ref, () => ({
      uploadFiles,
      clear: () => onChange([]),
    }));

    const handlePaste = (e: React.ClipboardEvent) => {
      const items = Array.from(e.clipboardData?.items || []);
      const files = items
        .filter((it) => it.kind === "file")
        .map((it) => it.getAsFile())
        .filter((f): f is File => Boolean(f));
      if (files.length > 0) {
        e.preventDefault();
        void uploadFiles(files);
      }
    };

    return (
      <div className="space-y-2" onPaste={handlePaste}>
        <div
          tabIndex={0}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            const files = Array.from(e.dataTransfer.files || []);
            void uploadFiles(files);
          }}
          className={`flex items-center justify-between gap-3 rounded-md border border-dashed border-input bg-card hover:bg-muted/50 transition-colors duration-75 focus:outline-none focus:ring-2 focus:ring-ring ${
            compact ? "px-3 py-2" : "px-4 py-2.5"
          }`}
        >
          <div className="flex items-center gap-2 text-meta min-w-0">
            {uploading ? (
              <Loader2 className="size-4 text-muted-foreground animate-spin shrink-0" strokeWidth={1.5} />
            ) : (
              <ClipboardPaste className="size-4 text-muted-foreground shrink-0" strokeWidth={1.5} />
            )}
            <span className="truncate">
              Nhấn Ctrl+V để dán ảnh chụp màn hình hoặc kéo thả tệp vào đây.
            </span>
          </div>

          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => inputRef.current?.click()}
            disabled={uploading}
          >
            <Paperclip className="size-3.5" strokeWidth={1.5} />
            <span>Chọn tệp</span>
          </Button>

          <input
            ref={inputRef}
            type="file"
            multiple
            accept="image/*,.pdf,.log,.txt,.xlsx,.docx"
            className="hidden"
            onChange={(e) => {
              const files = Array.from(e.target.files || []);
              void uploadFiles(files);
              e.target.value = "";
            }}
          />
        </div>

        {error && (
          <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-1.5 text-[13px] text-destructive">
            {error}
          </div>
        )}

        {attachments.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {attachments.map((att) => {
              const isImage = att.content_type.startsWith("image/");
              return (
                <div
                  key={att.id}
                  className="relative flex items-center gap-2 rounded-sm border border-border bg-card p-1.5 pr-7"
                >
                  {isImage ? (
                    <img
                      src={buildAttachmentUrl(att.download_url)}
                      alt={att.file_name}
                      className="size-10 object-cover rounded-xs border border-border-subtle"
                    />
                  ) : (
                    <div className="size-10 rounded-xs bg-muted flex items-center justify-center text-muted-foreground">
                      <FileImage className="size-4" strokeWidth={1.5} />
                    </div>
                  )}
                  <div className="max-w-[140px]">
                    <p className="text-[13px] font-medium text-foreground truncate">
                      {att.file_name}
                    </p>
                    <p className="text-[12px] text-faint tabular-nums">
                      {(att.size_bytes / 1024).toFixed(1)} KB
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => onChange(attachments.filter((item) => item.id !== att.id))}
                    className="absolute top-1 right-1 p-0.5 rounded-xs text-faint hover:text-foreground hover:bg-muted"
                    title="Gỡ tệp"
                  >
                    <X className="size-3.5" strokeWidth={1.5} />
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>
    );
  }
);
