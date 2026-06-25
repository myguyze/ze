import { lazy, Suspense, type ComponentType } from "react";
import { createBrowserRouter } from "react-router-dom";
import { AppShell } from "@/widgets/app-shell";
import { appRoutes, settingsRoute } from "./routes";

function lazyPage(loader: () => Promise<{ default: ComponentType }>) {
  const Lazy = lazy(loader);
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center h-full text-sm text-smoke">Loading…</div>
      }
    >
      <Lazy />
    </Suspense>
  );
}

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      ...appRoutes.map((route) =>
        route.index
          ? { index: true as const, element: lazyPage(route.lazy) }
          : { path: route.path, element: lazyPage(route.lazy) },
      ),
      { path: settingsRoute.path, element: lazyPage(settingsRoute.lazy) },
    ],
  },
]);
