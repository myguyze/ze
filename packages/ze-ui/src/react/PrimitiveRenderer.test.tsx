import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { PrimitiveRenderer } from "./PrimitiveRenderer";

describe("PrimitiveRenderer", () => {
  it("renders a text primitive", () => {
    render(<PrimitiveRenderer node={{ type: "text", content: "Hello world" }} />);
    expect(screen.getByText("Hello world")).toBeInTheDocument();
  });

  it("renders a table primitive", () => {
    render(
      <PrimitiveRenderer
        node={{
          type: "table",
          headers: ["Agent", "Cost"],
          rows: [["research", "$0.50"]],
          title: "Spend",
        }}
      />,
    );
    expect(screen.getByText("Spend")).toBeInTheDocument();
    expect(screen.getByText("research")).toBeInTheDocument();
  });

  it("renders a col with nested text children", () => {
    render(
      <PrimitiveRenderer
        node={{
          type: "col",
          children: [
            { type: "text", content: "$1.23", style: "heading" },
            { type: "text", content: "Total cost", style: "label" },
          ],
        }}
      />,
    );
    expect(screen.getByText("$1.23")).toBeInTheDocument();
    expect(screen.getByText("Total cost")).toBeInTheDocument();
  });

  it("renders a badge", () => {
    render(<PrimitiveRenderer node={{ type: "badge", label: "done", color: "success" }} />);
    expect(screen.getByText("done")).toBeInTheDocument();
  });

  it("renders a row with badges", () => {
    render(
      <PrimitiveRenderer
        node={{
          type: "row",
          children: [
            { type: "badge", label: "A" },
            { type: "badge", label: "B" },
          ],
        }}
      />,
    );
    expect(screen.getByText("A")).toBeInTheDocument();
    expect(screen.getByText("B")).toBeInTheDocument();
  });

  it("renders a connections primitive", () => {
    render(
      <PrimitiveRenderer
        node={{
          type: "connections",
          title: "Linked insights",
          connections: [
            {
              summary: "You work late before deadlines",
              narrative: "Seen in 3 episodes",
              relation: "pattern",
              confidence: 0.8,
            },
          ],
        }}
      />,
    );
    expect(screen.getByText("Linked insights")).toBeInTheDocument();
    expect(screen.getByText("You work late before deadlines")).toBeInTheDocument();
  });
});
