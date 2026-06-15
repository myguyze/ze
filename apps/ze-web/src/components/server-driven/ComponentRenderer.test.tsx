import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ComponentRenderer } from "./ComponentRenderer";

describe("ComponentRenderer", () => {
  it("renders a metric component", () => {
    render(
      <ComponentRenderer
        data={{ type: "metric", label: "Total cost", value: "$1.23" }}
      />,
    );
    expect(screen.getByText("$1.23")).toBeInTheDocument();
    expect(screen.getByText("Total cost")).toBeInTheDocument();
  });

  it("renders a table component", () => {
    render(
      <ComponentRenderer
        data={{
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
});
