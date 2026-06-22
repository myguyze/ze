import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PrimitiveTreeRenderer } from "@ze/ui/react";
import { useOnboardingSession } from "@/features/onboarding/useOnboardingSession";
import { usePrimitiveRendererActions } from "./usePrimitiveRendererActions";

const send = vi.fn();

vi.mock("@/features/websocket/useWebSocket", () => ({
  send: (...args: unknown[]) => {
    send(...args);
    return true;
  },
}));

vi.mock("@/features/websocket/useSendNotice", () => ({
  useSendNotice: (selector: (s: { showNotice: () => void }) => unknown) =>
    selector({ showNotice: vi.fn() }),
}));

vi.mock("@/features/chat/hooks/useSession", () => ({
  useSession: (selector: (s: { threadId: string }) => unknown) =>
    selector({ threadId: "ze-test-thread" }),
}));

function ConnectedFormTree({ node }: { node: Parameters<typeof PrimitiveTreeRenderer>[0]["nodes"][number] }) {
  const actions = usePrimitiveRendererActions();
  return <PrimitiveTreeRenderer nodes={[node]} actions={actions} />;
}

const formNode = {
  type: "form" as const,
  id: "profile.name",
  title: "Your name",
  fields: [{ id: "name", label: "Name", field_type: "text" as const }],
};

describe("form primitive via ConnectedPrimitiveTree", () => {
  beforeEach(() => {
    send.mockClear();
    useOnboardingSession.getState().clear();
  });

  it("sends component_submit with onboarding session when active", () => {
    useOnboardingSession.getState().setSession("onb-123", false);
    render(<ConnectedFormTree node={formNode} />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Ada" } });
    fireEvent.click(screen.getByRole("button", { name: "Submit" }));
    expect(send).toHaveBeenCalledWith({
      type: "component_submit",
      session_id: "onb-123",
      step_id: "profile.name",
      values: { name: "Ada" },
    });
  });

  it("sends component_submit with thread_id when not in onboarding", () => {
    render(<ConnectedFormTree node={formNode} />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Ada" } });
    fireEvent.click(screen.getByRole("button", { name: "Submit" }));
    expect(send).toHaveBeenCalledWith({
      type: "component_submit",
      step_id: "profile.name",
      values: { name: "Ada" },
      thread_id: "ze-test-thread",
    });
  });

  it("falls back to message when form has no id", () => {
    render(
      <ConnectedFormTree
        node={{
          type: "form",
          id: "",
          title: "Legacy",
          fields: [{ id: "x", label: "X", field_type: "text" }],
        }}
      />,
    );
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: "Submit" }));
    expect(send).toHaveBeenCalledWith({
      type: "message",
      text: '[form] {"x":"1"}',
    });
  });
});
