import { Bell, CheckCheck, Loader2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { NotificationItem } from "@myguyze/ze-client";
import {
  useMarkAllReadMutation,
  useMarkReadMutation,
  useNotificationsQuery,
  useUnreadCountQuery,
} from "@/entities/notification";
import { EmptyState } from "@/shared/ui";
import { cn } from "@/shared/lib/cn";
import { relativeTime, targetRoute } from "../lib/format";

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  const { data: unreadCount } = useUnreadCountQuery();
  const {
    data,
    isLoading,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useNotificationsQuery({ markRead: open });
  const markRead = useMarkReadMutation();
  const markAllRead = useMarkAllReadMutation();

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  const items = data?.pages.flatMap((p) => p.items) ?? [];

  function handleItemClick(item: NotificationItem) {
    if (!item.read) void markRead.mutate(item.id);
    const route = targetRoute(item.target_type, item.target_id);
    if (route) {
      setOpen(false);
      navigate(route);
    }
  }

  return (
    <div className="relative" ref={containerRef}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="relative flex items-center justify-center w-9 h-9 rounded-pill text-smoke hover:text-white hover:bg-white/5 transition-colors"
        aria-label="Notifications"
      >
        <Bell className="w-[18px] h-[18px]" />
        {!!unreadCount && unreadCount > 0 && (
          <span className="absolute top-1 right-1 min-w-[16px] h-[16px] px-1 rounded-full bg-plum-voltage text-[10px] leading-[16px] text-white text-center font-medium">
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-11 w-96 max-h-[28rem] flex flex-col rounded-2xl border border-white/10 bg-black shadow-xl z-50 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-white/[0.08]">
            <span className="text-sm font-semibold text-white">Notifications</span>
            <button
              onClick={() => markAllRead.mutate()}
              disabled={!unreadCount}
              className="flex items-center gap-1 text-xs text-smoke hover:text-white transition-colors disabled:opacity-40 disabled:hover:text-smoke"
            >
              <CheckCheck className="w-3.5 h-3.5" />
              Mark all read
            </button>
          </div>

          <div className="overflow-y-auto flex-1">
            {isLoading ? (
              <div className="flex items-center justify-center py-10">
                <Loader2 className="size-4 animate-spin text-smoke" />
              </div>
            ) : items.length === 0 ? (
              <EmptyState icon={Bell} message="You're all caught up." />
            ) : (
              <ul>
                {items.map((item) => (
                  <li key={item.id}>
                    <button
                      onClick={() => handleItemClick(item)}
                      className={cn(
                        "w-full text-left px-4 py-3 border-b border-white/[0.04] hover:bg-white/[0.03] transition-colors",
                        !item.read && "bg-plum-voltage/[0.06]",
                      )}
                    >
                      <div className="flex items-start gap-2">
                        {!item.read && (
                          <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-plum-voltage shrink-0" />
                        )}
                        <div className="min-w-0 flex-1">
                          <p className="text-sm text-white truncate">{item.title}</p>
                          <p className="text-xs text-smoke line-clamp-2 mt-0.5">{item.body}</p>
                          <p className="text-[11px] text-smoke/60 mt-1">
                            {relativeTime(item.created_at)} · {item.source}
                          </p>
                        </div>
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            )}

            {hasNextPage && (
              <button
                onClick={() => void fetchNextPage()}
                disabled={isFetchingNextPage}
                className="w-full py-2.5 text-xs text-smoke hover:text-white transition-colors"
              >
                {isFetchingNextPage ? "Loading…" : "Load more"}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
