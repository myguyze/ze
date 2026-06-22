import { describe, it, expect } from "vitest";
import {
  parsePrimitive,
  parsePrimitiveTree,
  validatePrimitive,
  PrimitiveValidationError,
} from "./index";

describe("parsePrimitiveTree", () => {
  it("accepts a valid primitive tree", () => {
    const tree = parsePrimitiveTree([
      { type: "text", content: "Hello" },
    ]);
    expect(tree).toHaveLength(1);
    expect(tree[0]?.type).toBe("text");
  });

  it("rejects unknown discriminators", () => {
    expect(() =>
      parsePrimitiveTree([{ type: "unknown_future_type" }]),
    ).toThrow(PrimitiveValidationError);
  });

  it("rejects missing required fields", () => {
    expect(() =>
      parsePrimitiveTree([{ type: "text" }]),
    ).toThrow(PrimitiveValidationError);
  });

  it("rejects invalid nested child nodes", () => {
    expect(() =>
      parsePrimitiveTree([
        {
          type: "col",
          children: [{ type: "text" }],
        },
      ]),
    ).toThrow(PrimitiveValidationError);

    try {
      parsePrimitiveTree([
        {
          type: "col",
          children: [{ type: "text" }],
        },
      ]);
    } catch (error) {
      expect(error).toBeInstanceOf(PrimitiveValidationError);
      const validationError = error as PrimitiveValidationError;
      expect(validationError.issues.length).toBeGreaterThan(0);
    }
  });

  it("exposes a type guard for valid primitives", () => {
    expect(validatePrimitive({ type: "divider" })).toBe(true);
    expect(validatePrimitive({ type: "not-real" })).toBe(false);
  });

  it("parses a single primitive node", () => {
    const node = parsePrimitive({ type: "badge", label: "ok" });
    expect(node.label).toBe("ok");
  });
});
