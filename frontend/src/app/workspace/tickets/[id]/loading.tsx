import { TicketDetailSkeleton, TopBarSkeleton } from "@/components/LoadingSkeletons";

export default function WorkspaceTicketLoading() {
  return (
    <div className="min-h-dvh flex flex-col bg-background text-foreground">
      <TopBarSkeleton />
      <TicketDetailSkeleton />
    </div>
  );
}
