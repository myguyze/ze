import { describe, it, expect } from "vitest";
import { send } from "./useWebSocket";

describe("send", () => {
  it("returns false when socket is not open", () => {
    expect(send({ type: "ping" })).toBe(false);
  });
});
