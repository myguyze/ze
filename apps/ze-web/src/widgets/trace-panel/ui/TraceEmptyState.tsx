import { Route } from "lucide-react";

export function TraceEmptyState() {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-3 px-4 py-8 text-center">
      <Route className="w-8 h-8 text-smoke/80" />
      <p className="text-xs text-smoke/80">No traces in this conversation yet</p>
    </div>
  );
}
