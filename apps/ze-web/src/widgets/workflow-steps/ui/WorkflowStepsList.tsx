import type { WorkflowStepResponse } from "@myguyze/ze-client";
import { CheckCircle2 } from "lucide-react";

interface Props {
  steps: WorkflowStepResponse[];
}

export function WorkflowStepsList({ steps }: Props) {
  if (!steps.length) {
    return <p className="text-sm text-smoke">No steps defined.</p>;
  }

  return (
    <ol className="space-y-3">
      {steps.map((step, i) => (
        <li key={i} className="flex gap-3">
          <div className="flex-shrink-0 w-6 h-6 rounded-full border border-white/20 flex items-center justify-center mt-0.5">
            <span className="text-xs text-smoke">{i + 1}</span>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm text-white">{step.task}</p>
            {step.agent_hint && (
              <p className="mt-0.5 text-xs text-smoke">Agent: {step.agent_hint}</p>
            )}
            {step.verify && (
              <div className="mt-1 flex items-start gap-1">
                <CheckCircle2 className="w-3 h-3 text-smoke flex-shrink-0 mt-0.5" />
                <p className="text-xs text-smoke">{step.verify}</p>
              </div>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}
