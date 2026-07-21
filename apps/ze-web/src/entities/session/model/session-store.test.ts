import { describe, it, expect, beforeEach } from "vitest";
import { useSession } from "./session-store";

describe("session-store highlight message", () => {
  beforeEach(() => {
    useSession.setState({ highlightMessageId: null });
  });

  it("setHighlightMessage sets the highlight target", () => {
    useSession.getState().setHighlightMessage("msg-1");
    expect(useSession.getState().highlightMessageId).toBe("msg-1");
  });

  it("selectSession switches the active thread", () => {
    useSession.getState().selectSession("sess-99");
    expect(useSession.getState().threadId).toBe("sess-99");
  });

  it("setHighlightMessage(null) clears the highlight", () => {
    useSession.getState().setHighlightMessage("msg-1");
    useSession.getState().setHighlightMessage(null);
    expect(useSession.getState().highlightMessageId).toBeNull();
  });
});
