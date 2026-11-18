"use client";

const SOUND_MUTED_KEY = "helpdesk_sound_muted";

export function isSoundMuted(): boolean {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(SOUND_MUTED_KEY) === "true";
}

export function setSoundMuted(muted: boolean): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(SOUND_MUTED_KEY, muted ? "true" : "false");
}

function playTone(
  ctx: AudioContext,
  freq: number,
  startOffsetSec: number,
  durationSec: number
) {
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = "sine";
  osc.frequency.setValueAtTime(freq, ctx.currentTime + startOffsetSec);

  gain.gain.setValueAtTime(0.001, ctx.currentTime + startOffsetSec);
  gain.gain.exponentialRampToValueAtTime(
    0.09,
    ctx.currentTime + startOffsetSec + 0.015
  );
  gain.gain.exponentialRampToValueAtTime(
    0.0001,
    ctx.currentTime + startOffsetSec + durationSec
  );

  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.start(ctx.currentTime + startOffsetSec);
  osc.stop(ctx.currentTime + startOffsetSec + durationSec);
}

export function playNotificationChime(urgent = false): void {
  if (typeof window === "undefined" || isSoundMuted()) return;
  const AudioCtx =
    window.AudioContext ||
    (window as unknown as { webkitAudioContext?: typeof AudioContext })
      .webkitAudioContext;
  if (!AudioCtx) return;

  try {
    const ctx = new AudioCtx();
    playTone(ctx, 880, 0, 0.11);
    if (urgent) {
      playTone(ctx, 1174.66, 0.12, 0.14);
    }
    window.setTimeout(() => {
      void ctx.close().catch(() => undefined);
    }, 500);
  } catch {
    // Ignore autoplay restriction before user interaction
  }
}

export function triggerDesktopNotification(
  title: string,
  body: string,
  href: string,
  onNavigate: (href: string) => void
): void {
  if (typeof window === "undefined" || !("Notification" in window)) return;
  if (Notification.permission !== "granted") return;

  try {
    const n = new Notification(title, {
      body,
      tag: href,
    });
    n.onclick = () => {
      window.focus();
      onNavigate(href);
      n.close();
    };
  } catch {
    // Ignore unsupported Notification environments
  }
}
