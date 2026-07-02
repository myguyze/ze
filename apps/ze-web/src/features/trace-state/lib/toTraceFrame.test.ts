import { describe, expect, it } from "vitest";
import type { MessageTraceResponse } from "@myguyze/ze-client";
import { toTraceFrame } from "./toTraceFrame";

describe("toTraceFrame", () => {
  it("maps REST trace response to WS trace frame", () => {
    const trace: MessageTraceResponse = {
      agent: "companion",
      routing_method: "embedding",
      confidence: 0.94,
      score_gap: 0.31,
      is_compound: false,
      subtasks: [],
      memory_chunks: [{ text: "User prefers concise answers", score: 0.91, source: "fact" }],
      tool_calls: [{ name: "search_web", result_snippet: "ok", duration_ms: 120, success: true }],
      total_duration_ms: 450,
    };

    expect(toTraceFrame("msg-1", trace)).toEqual({
      type: "trace_update",
      message_id: "msg-1",
      ...trace,
    });
  });
});
