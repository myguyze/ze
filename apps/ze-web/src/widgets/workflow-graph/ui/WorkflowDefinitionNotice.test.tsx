import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { WorkflowDefinitionNotice } from "./WorkflowDefinitionNotice";

describe("WorkflowDefinitionNotice", () => {
  it("renders a link that calls onViewRevisionsSince in historical-edited-since mode", () => {
    const onViewRevisionsSince = vi.fn();
    render(
      <WorkflowDefinitionNotice
        mode="historical-edited-since"
        startedAt="2026-07-10T00:00:00.000Z"
        onViewRevisionsSince={onViewRevisionsSince}
      />,
    );

    const link = screen.getByText("View changes since this run");
    fireEvent.click(link);
    expect(onViewRevisionsSince).toHaveBeenCalledTimes(1);
  });

  it("does not render the link in current mode even if the callback is provided", () => {
    const onViewRevisionsSince = vi.fn();
    render(<WorkflowDefinitionNotice mode="current" onViewRevisionsSince={onViewRevisionsSince} />);

    expect(screen.queryByText("View changes since this run")).not.toBeInTheDocument();
  });

  it("does not render the link when no callback is provided", () => {
    render(<WorkflowDefinitionNotice mode="historical-edited-since" startedAt="2026-07-10T00:00:00.000Z" />);

    expect(screen.queryByText("View changes since this run")).not.toBeInTheDocument();
  });
});
