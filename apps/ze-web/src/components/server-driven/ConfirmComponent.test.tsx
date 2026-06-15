import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ConfirmComponent } from "./ConfirmComponent";

const send = vi.fn();

vi.mock("@/features/websocket/useWebSocket", () => ({
  send: (...args: unknown[]) => send(...args),
}));

vi.mock("@/features/chat/hooks/useSession", () => ({
  useSession: (selector: (s: { threadId: string }) => unknown) =>
    selector({ threadId: "ze-test-thread" }),
}));

describe("ConfirmComponent", () => {
  beforeEach(() => {
    send.mockClear();
  });

  it("disables actions after one is chosen", () => {
    render(
      <ConfirmComponent
        data={{
          type: "confirm",
          prompt: "Proceed?",
          actions: [
            { label: "Yes", value: "yes" },
            { label: "No", value: "no" },
          ],
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Yes" }));

    expect(send).toHaveBeenCalledWith({
      type: "message",
      text: "yes",
      thread_id: "ze-test-thread",
    });
    expect(screen.getByRole("button", { name: "✓ Yes" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "No" })).toBeDisabled();
  });
});
