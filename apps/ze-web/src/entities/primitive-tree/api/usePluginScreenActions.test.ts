import { renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { invokeSdkOperation, showNotice, send } = vi.hoisted(() => ({
  invokeSdkOperation: vi.fn(),
  showNotice: vi.fn(),
  send: vi.fn(),
}));

vi.mock("@ze/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@ze/client")>();
  return {
    ...actual,
    invokeSdkOperation,
  };
});

vi.mock("@/features/send-context-notice", () => ({
  useSendNotice: (selector: (state: { showNotice: typeof showNotice }) => unknown) =>
    selector({ showNotice }),
}));

vi.mock("@/entities/onboarding-session", () => ({
  useOnboardingSession: (selector: (state: { sessionId: string | null; completed: boolean }) => unknown) =>
    selector({ sessionId: null, completed: true }),
}));

vi.mock("@/entities/session", () => ({
  useSession: (selector: (state: { threadId: string }) => unknown) =>
    selector({ threadId: "thread-1" }),
}));

vi.mock("@/shared/api", () => ({
  send,
}));

import { usePluginScreenActions } from "./usePluginScreenActions";

describe("usePluginScreenActions", () => {
  beforeEach(() => {
    invokeSdkOperation.mockReset();
    showNotice.mockReset();
    send.mockReset();
  });

  it("calls invokeSdkOperation and refetches on rest action success", async () => {
    invokeSdkOperation.mockResolvedValue({ title: "News", tree: [] });
    const onRestAction = vi.fn();

    const { result } = renderHook(() => usePluginScreenActions(onRestAction));
    result.current.onButtonAction?.("rest:getNewsPage");

    await vi.waitFor(() => {
      expect(invokeSdkOperation).toHaveBeenCalledWith("getNewsPage");
      expect(onRestAction).toHaveBeenCalled();
    });
  });

  it("shows notice when rest action fails", async () => {
    invokeSdkOperation.mockRejectedValue(new Error("boom"));
    const onRestAction = vi.fn();

    const { result } = renderHook(() => usePluginScreenActions(onRestAction));
    result.current.onButtonAction?.("rest:getNewsPage");

    await vi.waitFor(() => {
      expect(showNotice).toHaveBeenCalledWith("Action failed. Try again.");
      expect(onRestAction).not.toHaveBeenCalled();
    });
  });

  it("sends websocket message for msg actions", () => {
    const { result } = renderHook(() => usePluginScreenActions());
    result.current.onButtonAction?.("msg:Summarise news");

    expect(send).toHaveBeenCalledWith({
      type: "message",
      text: "Summarise news",
      thread_id: "thread-1",
    });
  });
});
