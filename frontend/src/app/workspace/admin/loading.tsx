import { AdminPageSkeleton, TopBarSkeleton } from "@/components/LoadingSkeletons";

export default function AdminLoading() {
  return (
    <div className="min-h-dvh flex flex-col bg-background text-foreground">
      <TopBarSkeleton />
      <AdminPageSkeleton />
    </div>
  );
}
