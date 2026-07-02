import { describe, expect, it } from "vitest";
import { pickZeErrorCopy, seedFromError } from "./ze-error-copy";

describe("pickZeErrorCopy", () => {
  it("returns stable copy for the same seed", () => {
    expect(pickZeErrorCopy(2)).toEqual(pickZeErrorCopy(2));
  });

  it("cycles through headline/subtext pairs", () => {
    const first = pickZeErrorCopy(0);
    const second = pickZeErrorCopy(1);
    expect(first.headline).not.toBe(second.headline);
  });
});

describe("seedFromError", () => {
  it("derives a deterministic seed from the error message", () => {
    const error = new Error("Cannot access 'threadId' before initialization");
    expect(seedFromError(error)).toBe(seedFromError(error));
  });
});
