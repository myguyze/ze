import { describe, expect, it } from "vitest";
import { parseSearchSnippet } from "./parseSearchSnippet";

describe("parseSearchSnippet", () => {
  it("splits ts_headline bold segments", () => {
    expect(parseSearchSnippet("your <b>calendar</b> tomorrow")).toEqual([
      { text: "your ", highlight: false },
      { text: "calendar", highlight: true },
      { text: " tomorrow", highlight: false },
    ]);
  });
});
