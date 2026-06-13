import { useQuery } from "@tanstack/react-query";
import { Target } from "lucide-react";
import { api } from "@/lib/api";
import { FloatingButton } from "@/overlay/FloatingButton";

interface Goal {
  id: string;
  objective: string;
  status: string;
  created_at: string;
}

export function GoalsScreen() {
  const { data: goals, isLoading } = useQuery({
    queryKey: ["goals"],
    queryFn: () => api.get<Goal[]>("/api/goals"),
  });

  return (
    <div className="px-4 py-8 space-y-6">
      <div>
        <p className="text-xs font-semibold tracking-widest uppercase text-[#9a9a9a] mb-1">
          Goals
        </p>
        <p className="text-2xl font-extralight text-white">Active goals</p>
      </div>

      {isLoading && (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-16 rounded-[24px] border border-white/10 animate-pulse" />
          ))}
        </div>
      )}

      {goals?.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20 gap-3 text-center">
          <Target className="w-8 h-8 text-[#9a9a9a]" />
          <p className="text-sm text-[#9a9a9a]">No active goals. Ask Ze to set one.</p>
        </div>
      )}

      {goals && goals.length > 0 && (
        <div className="space-y-3">
          {goals.map((goal) => (
            <div
              key={goal.id}
              className="p-4 rounded-[24px] border border-white/10 hover:border-white/20 transition-colors cursor-pointer"
            >
              <p className="text-sm text-white">{goal.objective}</p>
              <span className="mt-2 inline-block px-2 py-0.5 rounded-full border border-[#8052ff]/50 text-[#8052ff] text-xs">
                {goal.status}
              </span>
            </div>
          ))}
        </div>
      )}

      <FloatingButton screen="goals" />
    </div>
  );
}
