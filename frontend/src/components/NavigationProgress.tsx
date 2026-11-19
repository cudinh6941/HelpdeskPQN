"use client";

import React, {
  Suspense,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { usePathname, useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";

type Phase = "idle" | "loading" | "completing";

interface NavigationProgressContextValue {
  isNavigating: boolean;
  pendingPath: string | null;
  startNavigation: (targetPath?: string) => void;
}

const NavigationProgressContext = createContext<NavigationProgressContextValue>({
  isNavigating: false,
  pendingPath: null,
  startNavigation: () => {},
});

function getTransitionLabel(targetPath: string | null): string {
  if (!targetPath) return "Loading...";
  if (
    targetPath.startsWith("/workspace/tickets/") ||
    targetPath.startsWith("/portal/tickets/")
  ) {
    return "Opening ticket...";
  }
  if (targetPath.startsWith("/workspace/kb")) return "Loading knowledge base...";
  if (targetPath.startsWith("/workspace/analytics")) return "Loading analytics...";
  if (targetPath.startsWith("/workspace/admin")) return "Loading settings...";
  if (targetPath.startsWith("/workspace")) return "Loading queue...";
  if (targetPath.startsWith("/portal")) return "Loading portal...";
  if (targetPath.startsWith("/login")) return "Opening sign in...";
  return "Loading...";
}

function RouteSettledWatcher({ onRouteChange }: { onRouteChange: () => void }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const searchKey = searchParams?.toString() ?? "";
  const isFirstRender = useRef(true);

  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }
    onRouteChange();
  }, [pathname, searchKey, onRouteChange]);

  return null;
}

export function NavigationProgressProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const [phase, setPhase] = useState<Phase>("idle");
  const [progress, setProgress] = useState(0);
  const [showVeil, setShowVeil] = useState(false);
  const [pendingPath, setPendingPath] = useState<string | null>(null);

  const timersRef = useRef<number[]>([]);
  const phaseRef = useRef<Phase>("idle");

  const clearAllTimers = useCallback(() => {
    for (const id of timersRef.current) {
      window.clearTimeout(id);
      window.clearInterval(id);
    }
    timersRef.current = [];
  }, []);

  const finishNavigation = useCallback(() => {
    if (phaseRef.current === "idle") return;
    clearAllTimers();
    phaseRef.current = "completing";
    setPhase("completing");
    setProgress(100);
    setShowVeil(false);

    const resetTimer = window.setTimeout(() => {
      phaseRef.current = "idle";
      setPhase("idle");
      setProgress(0);
      setPendingPath(null);
    }, 220);
    timersRef.current.push(resetTimer);
  }, [clearAllTimers]);

  const startNavigation = useCallback(
    (targetPath?: string) => {
      if (typeof window === "undefined") return;
      if (targetPath) {
        const currentFull = `${window.location.pathname}${window.location.search}`;
        if (targetPath === currentFull || targetPath === window.location.pathname) {
          return;
        }
      }

      clearAllTimers();
      phaseRef.current = "loading";
      setPhase("loading");
      setPendingPath(targetPath ?? null);
      setProgress(18);
      setShowVeil(false);

      const veilTimer = window.setTimeout(() => {
        if (phaseRef.current === "loading") {
          setShowVeil(true);
        }
      }, 120);

      const trickleTimer = window.setInterval(() => {
        setProgress((prev) => {
          if (prev >= 88) return prev;
          const step = prev < 45 ? 14 : prev < 70 ? 7 : 3;
          return Math.min(88, prev + step);
        });
      }, 180);

      const safetyTimer = window.setTimeout(() => {
        finishNavigation();
      }, 8000);

      timersRef.current.push(veilTimer, trickleTimer, safetyTimer);
    },
    [clearAllTimers, finishNavigation]
  );

  useEffect(() => {
    const handleDocumentClick = (e: MouseEvent) => {
      if (
        e.defaultPrevented ||
        e.button !== 0 ||
        e.metaKey ||
        e.ctrlKey ||
        e.shiftKey ||
        e.altKey
      ) {
        return;
      }

      const target = e.target as HTMLElement | null;
      const anchor = target?.closest("a[href]") as HTMLAnchorElement | null;
      if (!anchor) return;
      if (anchor.target && anchor.target !== "_self") return;
      if (anchor.hasAttribute("download")) return;

      const rawHref = anchor.getAttribute("href");
      if (!rawHref || rawHref.startsWith("#") || rawHref.startsWith("mailto:") || rawHref.startsWith("tel:")) {
        return;
      }

      try {
        const nextUrl = new URL(anchor.href, window.location.href);
        if (nextUrl.origin !== window.location.origin) return;
        const nextFull = `${nextUrl.pathname}${nextUrl.search}`;
        const currFull = `${window.location.pathname}${window.location.search}`;
        if (nextFull === currFull) return;
        startNavigation(nextUrl.pathname);
      } catch {
        // Ignore malformed URLs
      }
    };

    document.addEventListener("click", handleDocumentClick, true);
    return () => {
      document.removeEventListener("click", handleDocumentClick, true);
      clearAllTimers();
    };
  }, [startNavigation, clearAllTimers]);

  const hasHeaderOffset = pathname !== "/" && pathname !== "/login";

  return (
    <NavigationProgressContext.Provider
      value={{
        isNavigating: phase === "loading",
        pendingPath,
        startNavigation,
      }}
    >
      <Suspense fallback={null}>
        <RouteSettledWatcher onRouteChange={finishNavigation} />
      </Suspense>

      {/* Top linear progress bar */}
      <div
        aria-hidden
        className="fixed top-0 left-0 right-0 z-[60] h-[2px] pointer-events-none"
      >
        <div
          className="h-full bg-ring"
          style={{
            width: `${progress}%`,
            opacity: phase === "loading" ? 1 : 0,
            transition:
              phase === "completing"
                ? "width 140ms cubic-bezier(0.22, 1, 0.36, 1), opacity 140ms ease-out 100ms"
                : "width 200ms cubic-bezier(0.22, 1, 0.36, 1), opacity 120ms ease-out",
          }}
        />
      </div>

      {/* Delayed subtle veil + floating status pill for slower transitions */}
      {phase === "loading" && showVeil && (
        <>
          <div
            aria-hidden
            className={`fixed inset-x-0 bottom-0 z-40 bg-background/45 backdrop-blur-[1px] pointer-events-none anim-scrim ${
              hasHeaderOffset ? "top-11" : "top-0"
            }`}
          />
          <div
            role="status"
            aria-live="polite"
            className={`fixed left-1/2 -translate-x-1/2 z-50 anim-popover rounded-md border border-border bg-card px-3 py-1.5 shadow-popover flex items-center gap-2 text-[13px] font-medium text-foreground pointer-events-none ${
              hasHeaderOffset ? "top-[54px]" : "top-4"
            }`}
          >
            <Loader2
              className="size-3.5 animate-spin text-ring shrink-0"
              strokeWidth={1.75}
            />
            <span>{getTransitionLabel(pendingPath)}</span>
          </div>
        </>
      )}

      {children}
    </NavigationProgressContext.Provider>
  );
}

export function useNavigationProgress() {
  return useContext(NavigationProgressContext);
}
