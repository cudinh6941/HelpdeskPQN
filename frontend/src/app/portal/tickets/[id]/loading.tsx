import { TicketDetailSkeleton, TopBarSkeleton } from "@/components/LoadingSkeletons";

export default function PortalTicketLoading() {
  return (
    <div className="min-h-dvh flex flex-col bg-background text-foreground">
      <TopBarSkeleton />
      <TicketDetailSkeleton twoColumn />
    </div>
  );
}
