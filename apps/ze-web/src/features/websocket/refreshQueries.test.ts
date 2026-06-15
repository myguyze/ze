import { describe, it, expect } from "vitest";
import { queryKeysForRefreshScreen } from "./refreshQueries";

describe("queryKeysForRefreshScreen", () => {
  it("returns query keys for known screens", () => {
    expect(queryKeysForRefreshScreen("goals")).toEqual(["goals"]);
    expect(queryKeysForRefreshScreen("contacts")).toEqual(["contacts"]);
  });

  it("returns undefined for unknown screens", () => {
    expect(queryKeysForRefreshScreen("chat")).toBeUndefined();
    expect(queryKeysForRefreshScreen("")).toBeUndefined();
  });
});
