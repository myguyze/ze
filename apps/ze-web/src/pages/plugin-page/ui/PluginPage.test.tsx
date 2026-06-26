import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { UiContribution, UiManifest } from "@/entities/ui-manifest";
import { PluginPage } from "./PluginPage";

const { useParams, useUiManifestQuery } = vi.hoisted(() => ({
  useParams: vi.fn(),
  useUiManifestQuery: vi.fn(),
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useParams,
    Navigate: ({ to }: { to: string }) => <div data-testid="navigate">{to}</div>,
  };
});

vi.mock("@/entities/ui-manifest", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/entities/ui-manifest")>();
  return {
    ...actual,
    useUiManifestQuery,
  };
});

vi.mock("@/widgets/plugin-screen", () => ({
  PluginScreen: ({ entry }: { entry: UiContribution }) => (
    <div data-testid="plugin-screen">{entry.label}</div>
  ),
}));

const newsEntry: UiContribution = {
  id: "ze_news.overview",
  plugin: "ze_news",
  kind: "nav",
  label: "News",
  icon: "newspaper",
  path: "news",
  page_operation_id: "getNewsPage",
  show_in_mobile_nav: true,
  priority: 100,
};

const manifest: UiManifest = {
  nav: [newsEntry],
  settings_sections: [],
};

describe("PluginPage", () => {
  it("renders PluginScreen when manifest path matches", () => {
    useParams.mockReturnValue({ pluginPath: "news" });
    useUiManifestQuery.mockReturnValue({
      data: manifest,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    render(<PluginPage />);

    expect(screen.getByTestId("plugin-screen")).toHaveTextContent("News");
  });

  it("redirects when manifest path is unknown", () => {
    useParams.mockReturnValue({ pluginPath: "missing" });
    useUiManifestQuery.mockReturnValue({
      data: manifest,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    render(<PluginPage />);

    expect(screen.getByTestId("navigate")).toHaveTextContent("/");
  });

  it("shows error when manifest query fails", () => {
    useParams.mockReturnValue({ pluginPath: "news" });
    useUiManifestQuery.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      refetch: vi.fn(),
    });

    render(<PluginPage />);

    expect(screen.getByText("Could not load navigation.")).toBeInTheDocument();
  });
});
