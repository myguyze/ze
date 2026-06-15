import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { SettingsPage } from "./SettingsPage";

const reconnect = vi.fn();
const saveConfig = vi.fn();
const healthCheck = vi.fn();

vi.mock("@/config/AppConfig", () => ({
  getConfig: () => ({ serverUrl: "http://localhost:8000", apiKey: "secret" }),
  saveConfig: (...args: unknown[]) => saveConfig(...args),
  clearConfig: vi.fn(),
}));

vi.mock("@/features/websocket/useWebSocket", () => ({
  reconnect: () => reconnect(),
}));

vi.mock("@/lib/api", () => ({
  healthCheck: (...args: unknown[]) => healthCheck(...args),
}));

describe("SettingsPage", () => {
  beforeEach(() => {
    reconnect.mockClear();
    saveConfig.mockClear();
    healthCheck.mockResolvedValue(true);
  });

  it("saves config and reconnects on save", async () => {
    render(<SettingsPage />);

    fireEvent.click(screen.getByRole("button", { name: "Test" }));
    await waitFor(() => expect(healthCheck).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: "Save & reconnect" }));

    expect(saveConfig).toHaveBeenCalledWith({
      serverUrl: "http://localhost:8000",
      apiKey: "secret",
    });
    expect(reconnect).toHaveBeenCalledOnce();
  });
});
