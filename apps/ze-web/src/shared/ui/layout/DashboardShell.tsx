import type { ReactNode } from "react";
import { cn } from "@/shared/lib/cn";
import { ErrorState } from "./ErrorState";
import { ListSkeleton } from "./ListSkeleton";
import { PageHeader } from "./PageHeader";
import { PageShell } from "./PageShell";

interface DashboardShellProps {
  label: string;
  title: string;
  children?: ReactNode;
  className?: string;
  isLoading?: boolean;
  isError?: boolean;
  errorMessage?: string;
  onRetry?: () => void;
  skeletonCount?: number;
}

export function DashboardShell({
  label,
  title,
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
      <PageHeader label={label} title={title} />

      {isLoading && (
        <div className="mt-8">
          <ListSkeleton count={skeletonCount} />
        </div>
      )}

      {isError && !isLoading && (
        <div className="mt-8">
          <ErrorState message={errorMessage} onRetry={onRetry ? () => void onRetry() : undefined} />
        </div>
      )}

      {!isLoading && !isError && children}
    </PageShell>
  );
}
