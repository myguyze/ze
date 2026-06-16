import { useEffect } from "react";
import { Outlet, NavLink, useNavigate } from "react-router-dom";
import { MessageCircle, Target, Bell, Users, BarChart2, Newspaper, Settings } from "lucide-react";
import { useOverlay } from "@/features/overlay/useOverlay";
import { ContextOverlay } from "@/features/overlay/ContextOverlay";
import { RefreshHandler } from "@/features/websocket/RefreshHandler";
import { NoticeBanner } from "@/components/layout/NoticeBanner";
import { cn } from "@/lib/cn";

const NAV_ITEMS = [
  { to: "/", icon: MessageCircle, label: "Chat", exact: true },
  { to: "/goals", icon: Target, label: "Goals" },
  { to: "/reminders", icon: Bell, label: "Reminders" },
  { to: "/contacts", icon: Users, label: "Contacts" },
  { to: "/costs", icon: BarChart2, label: "Usage" },
  { to: "/news", icon: Newspaper, label: "News" },
];

export function AppLayout() {
  const navigate = useNavigate();

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        useOverlay.getState().toggle();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="flex h-screen bg-black text-white overflow-hidden">
      <nav className="hidden md:flex flex-col w-14 lg:w-52 border-r border-white/10 flex-shrink-0">
        <div className="px-4 py-5 border-b border-white/10 flex items-center gap-3">
          <div className="w-6 h-6 rounded-full bg-[#8052ff] flex-shrink-0" />
          <span className="hidden lg:block text-sm font-semibold text-white">Ze</span>
        </div>

        <div className="flex-1 py-4 space-y-1 px-2">
          {NAV_ITEMS.map(({ to, icon: Icon, label, exact }) => (
            <NavLink
              key={to}
              to={to}
              end={exact}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 px-3 py-2 rounded-[24px] text-sm transition-colors",
                  isActive
                    ? "bg-[#8052ff]/15 text-white"
                    : "text-[#9a9a9a] hover:text-white hover:bg-white/5",
                )
              }
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              <span className="hidden lg:block">{label}</span>
            </NavLink>
          ))}
        </div>

        <div className="p-2 border-t border-white/10">
          <NavLink
            to="/settings"
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 px-3 py-2 rounded-[24px] text-sm transition-colors",
                isActive
                  ? "bg-[#8052ff]/15 text-white"
                  : "text-[#9a9a9a] hover:text-white hover:bg-white/5",
              )
            }
          >
            <Settings className="w-4 h-4 flex-shrink-0" />
            <span className="hidden lg:block">Settings</span>
          </NavLink>
        </div>
      </nav>

      <main className="flex-1 min-w-0 flex flex-col overflow-hidden">
        <NoticeBanner />
        <div className="flex-1 overflow-y-auto">
          <Outlet />
        </div>
      </main>

      <nav className="md:hidden fixed inset-x-0 bottom-0 z-30 flex border-t border-white/10 bg-black/90 backdrop-blur-sm">
        {NAV_ITEMS.slice(0, 5).map(({ to, icon: Icon, label, exact }) => (
          <NavLink
            key={to}
            to={to}
            end={exact}
            className={({ isActive }) =>
              cn(
                "flex-1 flex flex-col items-center py-3 gap-1 text-[10px] transition-colors",
                isActive ? "text-white" : "text-[#9a9a9a]",
              )
            }
          >
            <Icon className="w-5 h-5" />
            {label}
          </NavLink>
        ))}
        <button
          onClick={() => navigate("/settings")}
          className="flex-1 flex flex-col items-center py-3 gap-1 text-[10px] text-[#9a9a9a]"
        >
          <Settings className="w-5 h-5" />
          Settings
        </button>
      </nav>

      <RefreshHandler />
      <ContextOverlay />
    </div>
  );
}
