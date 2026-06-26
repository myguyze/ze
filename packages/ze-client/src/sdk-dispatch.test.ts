import { beforeEach, describe, expect, it, vi } from "vitest";

const { getNewsPage } = vi.hoisted(() => ({
  getNewsPage: vi.fn(),
}));

vi.mock("./generated/sdk.gen", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./generated/sdk.gen")>();
  return {
    ...actual,
    getNewsPage,
  };
});

import { invokeSdkOperation, loadPluginOperation } from "./sdk-dispatch";

describe("sdk-dispatch", () => {
  beforeEach(() => {
    getNewsPage.mockReset();
  });

  it("throws for unknown operation", async () => {
    await expect(invokeSdkOperation("missingOp")).rejects.toThrow("Unknown SDK operation");
  });

  it("returns PluginPageResponse from sdk function", async () => {
    getNewsPage.mockResolvedValue({ data: { title: "News", tree: [] } });
    const result = await loadPluginOperation("getNewsPage");
    expect(result).toEqual({ title: "News", tree: [] });
  });

  it("throws when sdk returns error", async () => {
    getNewsPage.mockResolvedValue({ error: { message: "fail" } });
    await expect(invokeSdkOperation("getNewsPage")).rejects.toThrow("SDK operation failed");
  });

  it("throws when response is not PluginPageResponse", async () => {
    getNewsPage.mockResolvedValue({ data: { foo: "bar" } });
    await expect(loadPluginOperation("getNewsPage")).rejects.toThrow(
      "did not return PluginPageResponse",
    );
  });
});
