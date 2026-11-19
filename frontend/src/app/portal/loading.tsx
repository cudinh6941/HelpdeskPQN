import { PortalPageSkeleton, TopBarSkeleton } from "@/components/LoadingSkeletons";

export default function PortalLoading() {
  return (
    <div className="min-h-dvh flex flex-col bg-background text-foreground">
      <TopBarSkeleton />
      <PortalPageSkeleton />
    </div>
  );
}
