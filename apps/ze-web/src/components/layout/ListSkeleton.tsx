interface ListSkeletonProps {
  count?: number;
  height?: string;
}

export function ListSkeleton({ count = 3, height = "h-16" }: ListSkeletonProps) {
  return (
    <div className="space-y-3">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className={`${height} rounded-pill border border-white/10 animate-pulse`} />
      ))}
    </div>
  );
}
