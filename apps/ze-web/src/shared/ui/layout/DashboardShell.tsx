import type { ReactNode } from "react";
import { cn } from "@/shared/lib/cn";
import { ErrorState } from "./ErrorState";
import { ListSkeleton } from "./ListSkeleton";
import { PageShell } from "./PageShell";

interface DashboardShellProps {
  children?: ReactNode;
  className?: string;
  isLoading?: boolean;
  isError?: boolean;
  errorMessage?: string;
  onRetry?: () => void;
  skeletonCount?: number;
}

export function DashboardShell({
  children,
  className,
  isLoading,
  isError,
  errorMessage = "Could not load data.",
  onRetry,
  skeletonCount,
}: DashboardShellProps) {
  return (
    <PageShell className={cn(className)}>
      {isLoading && <ListSkeleton count={skeletonCount} />}

      {isError && !isLoading && (
        <ErrorState message={errorMessage} onRetry={onRetry ? () => void onRetry() : undefined} />
      )}

      {!isLoading && !isError && children}
    </PageShell>
  );
}
