import type { BranchResponse, WorkflowStepResponse } from "@myguyze/ze-client";

function branchesEqual(a: BranchResponse[], b: BranchResponse[]): boolean {
  if (a.length !== b.length) return false;
  return a.every((branch, index) => {
    const other = b[index];
    return branch.condition === other.condition && branch.to === other.to;
  });
}

export function stepsDifferFromSnapshot(
  current: WorkflowStepResponse[],
  snapshot: WorkflowStepResponse[],
): boolean {
  if (current.length !== snapshot.length) return true;
  return current.some((step, index) => {
    const snap = snapshot[index];
    return (
      step.id !== snap.id ||
      step.task !== snap.task ||
      (step.on_failure ?? "fail") !== (snap.on_failure ?? "fail") ||
      !branchesEqual(step.branches, snap.branches)
    );
  });
}
