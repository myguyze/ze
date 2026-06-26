import { Brain } from "lucide-react";

export function MindEmptyState() {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-3 px-4 py-8 text-center">
      <Brain className="w-8 h-8 text-smoke/30" />
      <p className="text-xs text-smoke/60">
        Send a message to see Ze's thinking
      </p>
    </div>
  );
}
