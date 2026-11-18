"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { isItRole } from "@/lib/formatters";

export default function HomePage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    if (!user) {
      router.replace("/login");
    } else if (isItRole(user.role)) {
      router.replace("/workspace");
    } else {
      router.replace("/portal");
    }
  }, [user, loading, router]);

  return (
    <div className="min-h-dvh flex items-center justify-center bg-background text-meta-faint">
      Redirecting...
    </div>
  );
}
