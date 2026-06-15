import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MessageBubble } from "./MessageBubble";

describe("MessageBubble", () => {
  it("renders text and components in order", () => {
    render(
      <MessageBubble
        message={{
          id: "msg-1",
          role: "assistant",
          text: "Hello there",
          components: [{ type: "metric", label: "Spend", value: "$2.00" }],
          read: true,
          created_at: "2026-06-15T12:00:00.000Z",
          thread_id: "ze-thread",
        }}
      />,
    );

    expect(screen.getByText("Hello there")).toBeInTheDocument();
    expect(screen.getByText("$2.00")).toBeInTheDocument();
    expect(screen.getByText("Spend")).toBeInTheDocument();
  });
});
