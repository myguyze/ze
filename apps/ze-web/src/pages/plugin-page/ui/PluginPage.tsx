import { Navigate, useParams } from "react-router-dom";
import { useUiManifestQuery } from "@/entities/ui-manifest";
import { PluginScreen } from "@/widgets/plugin-screen";
import { ErrorState } from "@/shared/ui";

export function PluginPage() {
  const { pluginPath } = useParams<{ pluginPath: string }>();
  const { data: manifest, isLoading, isError, refetch } = useUiManifestQuery();

  if (!pluginPath) {
    return <Navigate to="/" replace />;
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-smoke">Loading…</div>
    );
  }

  if (isError) {
    return (
      <div className="px-4 py-8 max-w-2xl mx-auto">
        <ErrorState message="Could not load navigation." onRetry={() => void refetch()} />
      </div>
    );
  }

  const entry = manifest?.nav.find((item) => item.path === pluginPath);
  if (!entry) {
    return <Navigate to="/" replace />;
  }

  return <PluginScreen entry={entry} />;
}
