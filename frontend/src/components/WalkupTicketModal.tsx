"use client";

import React, { useEffect, useState } from "react";
import { Plus, X } from "lucide-react";

import {
  Button,
  Checkbox,
  inputBaseClass,
  selectBaseClass,
} from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { TicketDetail, TicketMetadata, TicketPriority } from "@/lib/types";

export function WalkupTicketModal({
  open,
  onClose,
  meta,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  meta: TicketMetadata | null;
  onCreated: (ticket: TicketDetail) => void;
}) {
  const [requesterId, setRequesterId] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [priority, setPriority] = useState<TicketPriority>("MEDIUM");
  const [title, setTitle] = useState("");
  const [assetCode, setAssetCode] = useState("");
  const [description, setDescription] = useState("");
  const [assignToMe, setAssignToMe] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !meta) return;
    setError(null);
    if (!requesterId && meta.requesters && meta.requesters.length > 0) {
      setRequesterId(meta.requesters[0].id);
    }
    if (!categoryId && meta.categories.length > 0) {
      setCategoryId(meta.categories[0].id);
      setPriority(meta.categories[0].default_priority);
    }
  }, [open, meta, requesterId, categoryId]);

  if (!open) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSaving(true);
    try {
      const created = await api.createTicket({
        title,
        description,
        category_id: categoryId || null,
        priority,
        asset_code: assetCode.trim() || undefined,
        requester_id: requesterId || null,
        assign_to_me: assignToMe,
      });
      setTitle("");
      setAssetCode("");
      setDescription("");
      onCreated(created);
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not create ticket.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      onClick={onClose}
      className="anim-scrim fixed inset-0 z-50 bg-[var(--scrim)] backdrop-blur-[2px] flex items-center justify-center p-4"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="anim-fade-up w-full max-w-[540px] rounded-lg border border-border bg-card shadow-popover overflow-hidden"
      >
        <div className="h-11 px-4 border-b border-border bg-background flex items-center justify-between">
          <span className="inline-flex items-center gap-2 text-body-strong">
            <Plus className="size-4 text-muted-foreground" strokeWidth={1.5} />
            <span>New walk-up / phone ticket</span>
          </span>
          <Button variant="icon" type="button" onClick={onClose} aria-label="Close modal">
            <X className="size-4" strokeWidth={1.5} />
          </Button>
        </div>

        <form onSubmit={handleSubmit} className="p-4 space-y-3">
          {error && (
            <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-[13px] text-destructive">
              {error}
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="space-y-1">
              <span className="block text-meta">Requester (Employee)</span>
              <select
                required
                value={requesterId}
                onChange={(e) => setRequesterId(e.target.value)}
                className={cn(selectBaseClass, "w-full h-9")}
              >
                {(meta?.requesters || []).map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.full_name} ({u.username})
                  </option>
                ))}
              </select>
            </label>

            <label className="space-y-1">
              <span className="block text-meta">Category</span>
              <select
                value={categoryId}
                onChange={(e) => {
                  const cid = e.target.value;
                  setCategoryId(cid);
                  const cat = meta?.categories.find((c) => c.id === cid);
                  if (cat) setPriority(cat.default_priority);
                }}
                className={cn(selectBaseClass, "w-full h-9")}
              >
                {(meta?.categories || []).map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="space-y-1">
            <label className="block text-meta">Title</label>
            <input
              type="text"
              required
              minLength={3}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Brief summary of the user's issue"
              className={cn(inputBaseClass, "h-9 text-[14px]")}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <label className="space-y-1">
              <span className="block text-meta">Asset code (optional)</span>
              <input
                type="text"
                value={assetCode}
                onChange={(e) => setAssetCode(e.target.value)}
                placeholder="PC-KT-012"
                className={cn(inputBaseClass, "h-9 text-[14px] font-mono")}
              />
            </label>

            <label className="space-y-1">
              <span className="block text-meta">Priority</span>
              <select
                value={priority}
                onChange={(e) => setPriority(e.target.value as TicketPriority)}
                className={cn(selectBaseClass, "w-full h-9")}
              >
                <option value="LOW">Low</option>
                <option value="MEDIUM">Medium</option>
                <option value="HIGH">High</option>
                <option value="CRITICAL">Urgent</option>
              </select>
            </label>
          </div>

          <div className="space-y-1">
            <label className="block text-meta">Description / Notes</label>
            <textarea
              required
              minLength={3}
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Details reported by phone or in person..."
              className={cn(inputBaseClass, "text-[14px]")}
            />
          </div>

          <label className="inline-flex items-center gap-2 pt-1 text-[13px] text-foreground cursor-pointer">
            <Checkbox
              checked={assignToMe}
              onChange={setAssignToMe}
              ariaLabel="Assign walk-up ticket to me"
            />
            <span>Assign to me &amp; start immediately (In Progress)</span>
          </label>

          <div className="flex items-center justify-end gap-2 pt-2 border-t border-border-subtle">
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={saving}>
              {saving ? "Creating..." : "Create ticket"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

