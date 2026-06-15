import { describe, it, expect } from "vitest";
import { refreshKeysForScreen } from "@/lib/queryKeys";

describe("refreshKeysForScreen", () => {
  it("returns query keys for known screens", () => {
    expect(refreshKeysForScreen("goals")).toEqual(["goals"]);
    expect(refreshKeysForScreen("contacts")).toEqual(["contacts"]);
  });

  it("returns undefined for unknown screens", () => {
    expect(refreshKeysForScreen("chat")).toBeUndefined();
    expect(refreshKeysForScreen("")).toBeUndefined();
  });
});
