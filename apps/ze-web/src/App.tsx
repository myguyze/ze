import { useState } from "react";
import { RouterProvider } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { hasConfig } from "./config/AppConfig";
import { OnboardingFlow } from "./screens/onboarding/OnboardingFlow";
import { router } from "./navigation/router";
import { startWs } from "./ws/useWebSocket";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
    },
  },
});

export function App() {
  const [configured, setConfigured] = useState(hasConfig);

  function handleOnboardingComplete() {
    setConfigured(true);
    startWs();
  }

  if (!configured) {
    return <OnboardingFlow onComplete={handleOnboardingComplete} />;
  }

  startWs();

  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}
