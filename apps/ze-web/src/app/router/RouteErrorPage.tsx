import { isRouteErrorResponse, useRouteError } from "react-router-dom";
import { ZeErrorFallback } from "@/shared/ui";

function toError(routeError: unknown): Error {
  if (routeError instanceof Error) return routeError;
  if (isRouteErrorResponse(routeError)) {
    return new Error(`${routeError.status} ${routeError.statusText}`);
  }
  return new Error(String(routeError ?? "Unknown route error"));
}

export function RouteErrorPage() {
  const routeError = useRouteError();
  const error = toError(routeError);

  return (
    <ZeErrorFallback
      error={error}
      onReset={() => {
        window.location.reload();
      }}
    />
  );
}
