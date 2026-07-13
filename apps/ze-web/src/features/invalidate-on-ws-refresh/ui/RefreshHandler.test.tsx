import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { queryKeys } from "@/shared/lib";
import { RefreshHandler } from "./RefreshHandler";

const { useFrame } = vi.hoisted(() => ({ useFrame: vi.fn() }));

vi.mock("@/shared/api", () => ({ useFrame }));

function getHandler(type: string) {
  const call = useFrame.mock.calls.find((c) => c[0] === type);
  return call?.[1] as (frame: unknown) => void;
}

describe("RefreshHandler — notification frame", () => {
  it("prepends a new notification to the cached first page and bumps unread count", () => {
    useFrame.mockClear();
    const queryClient = new QueryClient();
    const key = queryKeys.notifications(false);
    queryClient.setQueryData(key, {
      pages: [{ items: [{ id: "existing", title: "Old", body: "", event_type: "x", source: "x", target_type: null, target_id: null, created_at: "2026-01-01T00:00:00Z", read: false }], next_cursor: null }],
      pageParams: [undefined],
    });
    queryClient.setQueryData(queryKeys.unreadNotificationCount, 2);

    render(
      <QueryClientProvider client={queryClient}>
        <RefreshHandler />
      </QueryClientProvider>,
    );

    const handler = getHandler("notification");
    handler({
      type: "notification",
      id: "new-1",
      event_type: "stuck_goal",
      source: "goals",
      title: "Goal stuck",
      body: "body",
      target_type: "goal",
      target_id: "goal-a",
      created_at: "2026-07-13T00:00:00Z",
      read: false,
    });

    const data = queryClient.getQueryData<{ pages: { items: { id: string }[] }[] }>(key);
    expect(data?.pages[0]?.items[0]?.id).toBe("new-1");
    expect(data?.pages[0]?.items).toHaveLength(2);
    expect(queryClient.getQueryData(queryKeys.unreadNotificationCount)).toBe(3);
  });

  it("no-ops when no notifications query is cached yet", () => {
    useFrame.mockClear();
    const queryClient = new QueryClient();

    render(
      <QueryClientProvider client={queryClient}>
        <RefreshHandler />
      </QueryClientProvider>,
    );

    const handler = getHandler("notification");
    expect(() =>
      handler({
        type: "notification",
        id: "new-1",
        event_type: "stuck_goal",
        source: "goals",
        title: "Goal stuck",
        body: "body",
        target_type: null,
        target_id: null,
        created_at: "2026-07-13T00:00:00Z",
        read: false,
      }),
    ).not.toThrow();
  });
});
