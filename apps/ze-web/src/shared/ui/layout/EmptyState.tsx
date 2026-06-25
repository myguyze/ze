import { type LucideIcon } from "lucide-react";

interface EmptyStateProps {
  icon: LucideIcon;
  message: string;
  detail?: string;
}

export function EmptyState({ icon: Icon, message, detail }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
      <Icon className="w-8 h-8 text-smoke" />
      <p className="text-sm text-smoke">{message}</p>
      {detail && <p className="text-xs text-smoke max-w-xs">{detail}</p>}
    </div>
  );
}
