import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { EmptyState } from "./EmptyState";
import { ErrorState } from "./ErrorState";
import { ListSkeleton } from "./ListSkeleton";

interface ListPageProps {
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
  toolbar?: ReactNode;
  className?: string;
}

export function ListPage({
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
  toolbar,
  className = "px-6 md:px-10 py-8 space-y-8",
}: ListPageProps) {
  return (
    <div className={className}>
      {toolbar && <div>{toolbar}</div>}

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
