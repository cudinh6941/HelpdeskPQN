import { KbPageSkeleton, TopBarSkeleton } from "@/components/LoadingSkeletons";

export default function KbLoading() {
  return (
    <div className="min-h-dvh flex flex-col bg-background text-foreground">
      <TopBarSkeleton />
      <KbPageSkeleton />
    </div>
  );
}
