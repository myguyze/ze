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
      {
        path: "goals/:goalId",
        element: lazyPage(() =>
          import("@/pages/goal-detail").then((m) => ({ default: m.GoalDetailPage })),
        ),
      },
      {
        path: "workflows/:workflowId",
        element: lazyPage(() =>
          import("@/pages/workflow-detail").then((m) => ({ default: m.WorkflowDetailPage })),
        ),
      },
      { path: settingsRoute.path, element: lazyPage(settingsRoute.lazy) },
      { path: ":pluginPath", element: lazyPage(() => import("@/pages/plugin-page").then((m) => ({ default: m.PluginPage }))) },
    ],
  },
]);
