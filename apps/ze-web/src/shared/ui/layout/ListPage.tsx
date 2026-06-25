import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { EmptyState } from "./EmptyState";
import { ErrorState } from "./ErrorState";
import { ListSkeleton } from "./ListSkeleton";
import { PageHeader } from "./PageHeader";

interface ListPageProps {
  label: string;
  title: string;
  isLoading: boolean;
  isError: boolean;
  isEmpty: boolean;
  emptyIcon: LucideIcon;
  emptyMessage: string;
  emptyDetail?: string;
  errorMessage: string;
  errorDetail?: string;
  onRetry: () => void;
  skeletonCount?: number;
  skeletonHeight?: string;
  children: ReactNode;
  headerExtra?: ReactNode;
  className?: string;
}

export function ListPage({
  label,
  title,
  isLoading,
  isError,
  isEmpty,
  emptyIcon,
  emptyMessage,
  emptyDetail,
  errorMessage,
  errorDetail,
  onRetry,
  skeletonCount,
  skeletonHeight,
  children,
  headerExtra,
  className = "px-4 py-8 space-y-6",
}: ListPageProps) {
  return (
    <div className={className}>
      <div className="flex items-center justify-between gap-4">
        <PageHeader label={label} title={title} />
        {headerExtra}
      </div>

      {isLoading && <ListSkeleton count={skeletonCount} height={skeletonHeight} />}

      {isError && (
        <ErrorState message={errorMessage} detail={errorDetail} onRetry={onRetry} />
      )}

      {!isError && isEmpty && !isLoading && (
        <EmptyState icon={emptyIcon} message={emptyMessage} detail={emptyDetail} />
      )}

      {!isError && !isLoading && !isEmpty && children}
    </div>
  );
}
