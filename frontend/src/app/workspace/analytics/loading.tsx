import { AnalyticsPageSkeleton, TopBarSkeleton } from "@/components/LoadingSkeletons";

export default function AnalyticsLoading() {
  return (
    <div className="min-h-dvh flex flex-col bg-background text-foreground">
      <TopBarSkeleton />
      <AnalyticsPageSkeleton />
    </div>
  );
}
