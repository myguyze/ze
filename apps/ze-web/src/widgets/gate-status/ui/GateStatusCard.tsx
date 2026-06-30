import type { GateResponse } from "@myguyze/ze-client";
import { ShieldCheck, Clock, CheckCheck, XCircle } from "lucide-react";
import { Button } from "@/shared/ui";
import { useStartGoalMutation } from "@/entities/goal";

const STATUS_ICON: Record<string, React.ReactNode> = {
  awaiting_approval: <Clock className="w-4 h-4 text-amber-400" />,
  approved: <CheckCheck className="w-4 h-4 text-emerald-400" />,
  stopped: <XCircle className="w-4 h-4 text-red-400" />,
  redirected: <ShieldCheck className="w-4 h-4 text-blue-400" />,
  pending: <ShieldCheck className="w-4 h-4 text-smoke/50" />,
};

interface GateStatusCardProps {
  gate: GateResponse;
  goalId: string;
}

export function GateStatusCard({ gate, goalId }: GateStatusCardProps) {
  const startGoal = useStartGoalMutation();
  const isAwaiting = gate.status === "awaiting_approval";

  return (
    <div className="rounded-pill border border-white/10 p-4 space-y-2">
      <div className="flex items-center gap-2">
        {STATUS_ICON[gate.status] ?? STATUS_ICON.pending}
        <p className="text-sm font-medium text-white">{gate.title}</p>
      </div>

      {gate.context_summary && (
        <p className="text-xs text-smoke">{gate.context_summary}</p>
      )}

      {isAwaiting && (
        <div className="pt-1">
          <p className="text-xs text-smoke/60 mb-2">Awaiting your approval to continue.</p>
          <Button
            size="sm"
            disabled={startGoal.isPending}
            onClick={() => startGoal.mutate(goalId)}
          >
            {startGoal.isPending ? "Resuming…" : "Approve & continue"}
          </Button>
        </div>
      )}
    </div>
  );
}
