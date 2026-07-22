import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { LoopReviewList } from "./LoopReviewList";

const { useLoopsQuery, useLoopTransitionMutation } = vi.hoisted(() => ({
  useLoopsQuery: vi.fn(),
  useLoopTransitionMutation: vi.fn(),
}));

vi.mock("@/entities/loop", () => ({
  useLoopsQuery,
  useLoopTransitionMutation,
}));

const suspectedLoop = {
  id: "loop-1",
  title: "Renew passport before the trip",
  state: "suspected",
  claim_kind: "suspicion",
  provenance: "conversation",
  confidence: 0.35,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

const activeLoop = {
  ...suspectedLoop,
  id: "loop-2",
  title: "Follow up with the accountant",
  state: "active",
  provenance: "user_declared",
  confidence: 0.9,
};

function setup(loops: (typeof suspectedLoop)[], mutate = vi.fn()) {
  useLoopsQuery.mockReturnValue({
    data: loops,
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  });
  useLoopTransitionMutation.mockReturnValue({ mutate, isPending: false });
  return mutate;
}

describe("LoopReviewList", () => {
  it("shows the empty state when there are no loops", () => {
    setup([]);
    render(<LoopReviewList />);
    expect(screen.getByText("No open loops right now.")).toBeInTheDocument();
  });

  it("visibly distinguishes suspected from active rows", () => {
    setup([suspectedLoop, activeLoop]);
    render(<LoopReviewList />);

    expect(screen.getByText("Suspected")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
  });

  it("only offers Confirm on suspected loops", () => {
    setup([suspectedLoop, activeLoop]);
    render(<LoopReviewList />);

    expect(screen.getAllByText("Confirm")).toHaveLength(1);
    expect(screen.getAllByText("Close")).toHaveLength(1);
  });

  it("calls the transition mutation with confirm on click", () => {
    const mutate = setup([suspectedLoop]);
    render(<LoopReviewList />);

    fireEvent.click(screen.getByText("Confirm"));

    expect(mutate).toHaveBeenCalledWith({ loopId: "loop-1", kind: "confirm" });
  });

  it("calls the transition mutation with drop on click", () => {
    const mutate = setup([suspectedLoop]);
    render(<LoopReviewList />);

    fireEvent.click(screen.getByText("Drop"));

    expect(mutate).toHaveBeenCalledWith({ loopId: "loop-1", kind: "drop" });
  });
});
