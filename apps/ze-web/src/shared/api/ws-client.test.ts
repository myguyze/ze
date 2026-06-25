import { describe, it, expect } from "vitest";
import { send } from "./ws-client";

describe("send", () => {
  it("returns false when socket is not open", () => {
    expect(send({ type: "ping" })).toBe(false);
  });
});
