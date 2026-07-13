import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { NotificationBell } from "./NotificationBell";

const {
  useNotificationsQuery,
  useUnreadCountQuery,
  useMarkReadMutation,
  useMarkAllReadMutation,
} = vi.hoisted(() => ({
  useNotificationsQuery: vi.fn(),
  useUnreadCountQuery: vi.fn(),
  useMarkReadMutation: vi.fn(),
  useMarkAllReadMutation: vi.fn(),
}));

vi.mock("@/entities/notification", () => ({
  useNotificationsQuery,
  useUnreadCountQuery,
  useMarkReadMutation,
  useMarkAllReadMutation,
}));

function renderBell() {
  return render(
    <MemoryRouter>
      <NotificationBell />
    </MemoryRouter>,
  );
}

const item = {
  id: "notif-1",
  event_type: "stuck_goal",
  source: "goals",
  title: "Goal stuck",
  body: "Goal A hasn't moved in 3 days",
  target_type: "goal",
  target_id: "goal-a",
  created_at: new Date().toISOString(),
  read: false,
};

function setup({
  unreadCount = 0,
  items = [] as (typeof item)[],
}: { unreadCount?: number; items?: (typeof item)[] } = {}) {
  useUnreadCountQuery.mockReturnValue({ data: unreadCount });
  useNotificationsQuery.mockReturnValue({
    data: { pages: [{ items, next_cursor: null }] },
    isLoading: false,
    fetchNextPage: vi.fn(),
    hasNextPage: false,
    isFetchingNextPage: false,
  });
  useMarkReadMutation.mockReturnValue({ mutate: vi.fn() });
  useMarkAllReadMutation.mockReturnValue({ mutate: vi.fn() });
}

describe("NotificationBell", () => {
  it("shows the unread count badge", () => {
    setup({ unreadCount: 3 });
    renderBell();

    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("hides the badge when unread count is zero", () => {
    setup({ unreadCount: 0 });
    renderBell();

    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("shows the empty state when there are no notifications", () => {
    setup({ items: [] });
    renderBell();

    fireEvent.click(screen.getByLabelText("Notifications"));

    expect(screen.getByText("You're all caught up.")).toBeInTheDocument();
  });

  it("renders notification items when the panel is open", () => {
    setup({ items: [item] });
    renderBell();

    fireEvent.click(screen.getByLabelText("Notifications"));

    expect(screen.getByText("Goal stuck")).toBeInTheDocument();
    expect(screen.getByText("Goal A hasn't moved in 3 days")).toBeInTheDocument();
  });

  it("calls mark-all-read when the action is clicked", () => {
    const mutate = vi.fn();
    setup({ unreadCount: 2, items: [item] });
    useMarkAllReadMutation.mockReturnValue({ mutate });
    renderBell();

    fireEvent.click(screen.getByLabelText("Notifications"));
    fireEvent.click(screen.getByText("Mark all read"));

    expect(mutate).toHaveBeenCalled();
  });

  it("marks an unread item read on click", () => {
    const mutate = vi.fn();
    setup({ items: [item] });
    useMarkReadMutation.mockReturnValue({ mutate });
    renderBell();

    fireEvent.click(screen.getByLabelText("Notifications"));
    fireEvent.click(screen.getByText("Goal stuck"));

    expect(mutate).toHaveBeenCalledWith("notif-1");
  });
});
