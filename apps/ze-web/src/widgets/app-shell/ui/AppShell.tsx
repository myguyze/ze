import { Brain, Settings } from "lucide-react";
import { useEffect, useMemo } from "react";
import { Outlet, NavLink } from "react-router-dom";
import { mergeMobileNavRoutes, pluginNavRoutes, useUiManifestQuery } from "@/entities/ui-manifest";
import { RefreshHandler } from "@/features/invalidate-on-ws-refresh";
import { useOverlay } from "@/features/open-context-overlay";
import { NoticeBanner } from "@/features/send-context-notice";
import { brainNavRoutes, navRoutes, settingsNavRoute, standardNavRoutes } from "@/shared/config";
import { cn } from "@/shared/lib/cn";
import { BreadcrumbProvider } from "@/shared/lib/breadcrumb";
import { TopBar } from "@/shared/ui";
import { ChatNavGroup } from "./ChatNavGroup";
import { ContextOverlay } from "./ContextOverlay";
import { NavGroup } from "./NavGroup";

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    "flex items-center gap-3 px-3 py-2 rounded-pill text-sm transition-colors",
    isActive ? "bg-plum-voltage/15 text-white" : "text-smoke hover:text-white hover:bg-white/5",
  );

const childNavLinkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    "flex items-center gap-2.5 px-3 py-1.5 rounded-pill text-xs w-full transition-colors",
    isActive ? "bg-plum-voltage/15 text-white" : "text-smoke hover:text-white hover:bg-white/5",
  );

const mobileNavLinkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    "flex-1 flex flex-col items-center py-3 gap-1 text-[10px] transition-colors",
    isActive ? "text-white" : "text-smoke",
  );

export function AppShell() {
  const { data: uiManifest } = useUiManifestQuery();

  const mobileNavRoutes = useMemo(
    () => mergeMobileNavRoutes(navRoutes, settingsNavRoute, uiManifest?.nav),
    [uiManifest?.nav],
  );

  const pluginRoutes = useMemo(
    () => pluginNavRoutes(uiManifest?.nav ?? []),
    [uiManifest?.nav],
  );

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
          <div className="w-6 h-6 rounded-full bg-plum-voltage flex-shrink-0" />
          <span className="hidden lg:block text-sm font-semibold text-white">Ze</span>
        </div>

        <div className="flex-1 py-4 space-y-0.5 px-2 overflow-y-auto">
          {/* Chat + recent sessions */}
          <ChatNavGroup />

          {/* Standard routes: Goals, Workflows, Costs */}
          {standardNavRoutes.map(({ path, icon: Icon, label }) => (
            <NavLink key={path} to={path} className={navLinkClass}>
              <Icon className="w-4 h-4 flex-shrink-0" />
              <span className="hidden lg:block">{label}</span>
            </NavLink>
          ))}

          {/* Brain group: Memory, Activity, Graph */}
          <NavGroup
            icon={Brain}
            label="Brain"
            childPaths={brainNavRoutes.map((r) => r.path)}
          >
            {brainNavRoutes.map(({ path, icon: Icon, label }) => (
              <NavLink key={path} to={path} className={childNavLinkClass}>
                <Icon className="w-3.5 h-3.5 flex-shrink-0" />
                <span>{label}</span>
              </NavLink>
            ))}
          </NavGroup>

          {/* Plugin-contributed routes */}
          {pluginRoutes.map(({ path, icon: Icon, label }) => (
            <NavLink key={path} to={path} className={navLinkClass}>
              <Icon className="w-4 h-4 flex-shrink-0" />
              <span className="hidden lg:block">{label}</span>
            </NavLink>
          ))}
        </div>

        <div className="p-2 border-t border-white/10">
          <NavLink to={`/${settingsNavRoute.path}`} className={navLinkClass}>
            <Settings className="w-4 h-4 flex-shrink-0" />
            <span className="hidden lg:block">{settingsNavRoute.label}</span>
          </NavLink>
        </div>
      </nav>

      <main className="flex-1 min-w-0 flex flex-col overflow-hidden">
        <BreadcrumbProvider>
          <TopBar />
          <NoticeBanner />
          <div className="flex-1 overflow-y-auto pb-16 md:pb-0">
            <Outlet />
          </div>
        </BreadcrumbProvider>
      </main>

      <nav className="md:hidden fixed inset-x-0 bottom-0 z-30 flex border-t border-white/10 bg-black/90 backdrop-blur-sm">
        {mobileNavRoutes.map(({ path, icon: Icon, label, index }) => (
          <NavLink key={path} to={path} end={index} className={mobileNavLinkClass}>
            <Icon className="w-5 h-5" />
            {label}
          </NavLink>
        ))}
      </nav>

      <RefreshHandler />
      <ContextOverlay />
    </div>
  );
}
