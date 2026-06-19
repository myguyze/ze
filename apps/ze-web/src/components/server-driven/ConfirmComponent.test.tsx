import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PrimitiveRenderer } from "./PrimitiveRenderer";

const send = vi.fn();

vi.mock("@/features/websocket/useWebSocket", () => ({
  send: (...args: unknown[]) => { send(...args); return true; },
}));

vi.mock("@/features/websocket/useSendNotice", () => ({
  useSendNotice: (selector: (s: { showNotice: () => void }) => unknown) =>
    selector({ showNotice: vi.fn() }),
}));

vi.mock("@/features/chat/hooks/useSession", () => ({
  useSession: (selector: (s: { threadId: string }) => unknown) =>
    selector({ threadId: "ze-test-thread" }),
}));

// A confirm prompt is a col with prompt text + row of buttons, built by builders.confirm_prompt.
const confirmNode = {
  type: "col" as const,
  variant: "card" as const,
  children: [
    { type: "text" as const, content: "Proceed?" },
    {
      type: "row" as const,
      children: [
        { type: "button" as const, label: "Yes", action: "yes", style: "primary" as const },
        { type: "button" as const, label: "No", action: "no", style: "secondary" as const },
      ],
    },
  ],
};

describe("confirm prompt via PrimitiveRenderer", () => {
  beforeEach(() => {
    send.mockClear();
  });

  it("renders prompt and action buttons", () => {
    render(<PrimitiveRenderer node={confirmNode} />);
    expect(screen.getByText("Proceed?")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Yes" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "No" })).toBeInTheDocument();
  });

  it("sends action string as message on button click", () => {
    render(<PrimitiveRenderer node={confirmNode} />);
    fireEvent.click(screen.getByRole("button", { name: "Yes" }));
    expect(send).toHaveBeenCalledWith({
      type: "message",
      text: "yes",
      thread_id: "ze-test-thread",
    });
  });

  it("disables button after click and shows checkmark", () => {
    render(<PrimitiveRenderer node={confirmNode} />);
    fireEvent.click(screen.getByRole("button", { name: "Yes" }));
    expect(screen.getByRole("button", { name: "✓ Yes" })).toBeDisabled();
  });
});
