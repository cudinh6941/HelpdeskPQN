import { QueuePageSkeleton, TopBarSkeleton } from "@/components/LoadingSkeletons";

export default function WorkspaceLoading() {
  return (
    <div className="min-h-dvh flex flex-col bg-background text-foreground">
      <TopBarSkeleton />
      <QueuePageSkeleton />
    </div>
  );
}
