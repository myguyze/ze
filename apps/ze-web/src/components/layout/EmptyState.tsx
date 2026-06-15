import { type LucideIcon } from "lucide-react";

interface EmptyStateProps {
  icon: LucideIcon;
  message: string;
  detail?: string;
}

export function EmptyState({ icon: Icon, message, detail }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
      <Icon className="w-8 h-8 text-[#9a9a9a]" />
      <p className="text-sm text-[#9a9a9a]">{message}</p>
      {detail && <p className="text-xs text-[#9a9a9a] max-w-xs">{detail}</p>}
    </div>
  );
}
