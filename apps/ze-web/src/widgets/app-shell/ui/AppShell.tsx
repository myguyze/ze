import { Settings } from "lucide-react";
import { useEffect, useMemo } from "react";
import { Outlet, NavLink } from "react-router-dom";
import { mergeMobileNavRoutes, mergeNavRoutes, useUiManifestQuery } from "@/entities/ui-manifest";
import { RefreshHandler } from "@/features/invalidate-on-ws-refresh";
import { useOverlay } from "@/features/open-context-overlay";
import { NoticeBanner } from "@/features/send-context-notice";
import { navRoutes, settingsNavRoute } from "@/shared/config";
import { cn } from "@/shared/lib/cn";
import { BreadcrumbProvider } from "@/shared/lib/breadcrumb";
import { TopBar } from "@/shared/ui";
import { ContextOverlay } from "./ContextOverlay";

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    "flex items-center gap-3 px-3 py-2 rounded-pill text-sm transition-colors",
    isActive ? "bg-plum-voltage/15 text-white" : "text-smoke hover:text-white hover:bg-white/5",
  );

const mobileNavLinkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    "flex-1 flex flex-col items-center py-3 gap-1 text-[10px] transition-colors",
    isActive ? "text-white" : "text-smoke",
  );

export function AppShell() {
  const { data: uiManifest } = useUiManifestQuery();
  const desktopNavRoutes = useMemo(
    () => mergeNavRoutes(navRoutes, uiManifest?.nav),
    [uiManifest?.nav],
  );
  const mobileNavRoutes = useMemo(
    () => mergeMobileNavRoutes(navRoutes, settingsNavRoute, uiManifest?.nav),
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

        <div className="flex-1 py-4 space-y-1 px-2">
          {desktopNavRoutes.map(({ path, icon: Icon, label, index }) => (
            <NavLink key={path} to={path} end={index} className={navLinkClass}>
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
