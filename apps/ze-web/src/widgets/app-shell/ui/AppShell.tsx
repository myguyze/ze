import { Settings, Puzzle } from "lucide-react";
import { useEffect, useMemo } from "react";
import { Outlet, NavLink } from "react-router-dom";
import { mergeMobileNavRoutes, pluginNavRoutes, useUiManifestQuery } from "@/entities/ui-manifest";
import { RefreshHandler } from "@/features/invalidate-on-ws-refresh";
import { useOverlay } from "@/features/open-context-overlay";
import { NoticeBanner } from "@/features/send-context-notice";
import { WorkIcon, KnowledgeIcon, SystemIcon, workNavRoutes, knowledgeNavRoutes, systemNavRoutes, navRoutes, settingsNavRoute } from "@/shared/config";
import { cn } from "@/shared/lib/cn";
import { BreadcrumbProvider, TopBarActionsProvider } from "@/shared/lib";
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

          {/* Work group: Goals, Workflows */}
          <NavGroup
            icon={WorkIcon}
            label="Work"
            childPaths={workNavRoutes.map((r) => r.path)}
          >
            {workNavRoutes.map(({ path, icon: Icon, label }) => (
              <NavLink key={path} to={path} className={childNavLinkClass}>
                <Icon className="w-3.5 h-3.5 flex-shrink-0" />
                <span>{label}</span>
              </NavLink>
            ))}
          </NavGroup>

          {/* Knowledge group: Memory, Graph */}
          <NavGroup
            icon={KnowledgeIcon}
            label="Knowledge"
            childPaths={knowledgeNavRoutes.map((r) => r.path)}
          >
            {knowledgeNavRoutes.map(({ path, icon: Icon, label }) => (
              <NavLink key={path} to={path} className={childNavLinkClass}>
                <Icon className="w-3.5 h-3.5 flex-shrink-0" />
                <span>{label}</span>
              </NavLink>
            ))}
          </NavGroup>

          {/* System group: Usage, Activity */}
          <NavGroup
            icon={SystemIcon}
            label="System"
            childPaths={systemNavRoutes.map((r) => r.path)}
          >
            {systemNavRoutes.map(({ path, icon: Icon, label }) => (
              <NavLink key={path} to={path} className={childNavLinkClass}>
                <Icon className="w-3.5 h-3.5 flex-shrink-0" />
                <span>{label}</span>
              </NavLink>
            ))}
          </NavGroup>

          {/* Plugins group */}
          {pluginRoutes.length > 0 && (
            <NavGroup
              icon={Puzzle}
              label="Plugins"
              childPaths={pluginRoutes.map((r) => r.path)}
            >
              {pluginRoutes.map(({ path, icon: Icon, label }) => (
                <NavLink key={path} to={path} className={childNavLinkClass}>
                  <Icon className="w-3.5 h-3.5 flex-shrink-0" />
                  <span>{label}</span>
                </NavLink>
              ))}
            </NavGroup>
          )}
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
          <TopBarActionsProvider>
            <TopBar />
            <NoticeBanner />
            <div className="flex-1 overflow-y-auto pb-16 md:pb-0">
              <Outlet />
            </div>
          </TopBarActionsProvider>
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
