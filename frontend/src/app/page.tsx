"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { BrandBootScreen } from "@/components/LoadingSkeletons";
import { useNavigationProgress } from "@/components/NavigationProgress";
import { useAuth } from "@/lib/auth-context";
import { isItRole } from "@/lib/formatters";

export default function HomePage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const { startNavigation } = useNavigationProgress();

  useEffect(() => {
    if (loading) return;
    const target = !user
      ? "/login"
      : isItRole(user.role)
      ? "/workspace"
      : "/portal";
    startNavigation(target);
    router.replace(target);
  }, [user, loading, router, startNavigation]);

  return <BrandBootScreen label="Preparing workspace..." />;
}
