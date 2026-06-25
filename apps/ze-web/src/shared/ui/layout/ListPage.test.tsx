import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { Target } from "lucide-react";
import { ListPage } from "./ListPage";

describe("ListPage", () => {
  it("renders children when data is loaded", () => {
    render(
      <ListPage
        label="Goals"
        title="Active goals"
        isLoading={false}
        isError={false}
        isEmpty={false}
        emptyIcon={Target}
        emptyMessage="No goals"
        errorMessage="Failed"
        onRetry={vi.fn()}
      >
        <p>Goal list content</p>
      </ListPage>,
    );

    expect(screen.getByText("Active goals")).toBeInTheDocument();
    expect(screen.getByText("Goal list content")).toBeInTheDocument();
  });

  it("renders empty state when isEmpty", () => {
    render(
      <ListPage
        label="Goals"
        title="Active goals"
        isLoading={false}
        isError={false}
        isEmpty={true}
        emptyIcon={Target}
        emptyMessage="No active goals"
        errorMessage="Failed"
        onRetry={vi.fn()}
      >
        <p>Goal list content</p>
      </ListPage>,
    );

    expect(screen.getByText("No active goals")).toBeInTheDocument();
    expect(screen.queryByText("Goal list content")).not.toBeInTheDocument();
  });
});
