import { useEffect, useState } from "react";
import { RouterProvider } from "react-router-dom";
import { hasConfig } from "@/config/AppConfig";
import { OnboardingFlow } from "@/pages/onboarding/OnboardingFlow";
import { router } from "@/app/router";
import { Providers } from "@/app/providers";
import { startWs } from "@/features/websocket/useWebSocket";

export function App() {
  const [configured, setConfigured] = useState(hasConfig);

  useEffect(() => {
    if (configured) startWs();
  }, [configured]);

  function handleOnboardingComplete() {
    setConfigured(true);
  }

  return (
    <Providers>
      {!configured ? (
        <OnboardingFlow onComplete={handleOnboardingComplete} />
      ) : (
        <RouterProvider router={router} />
      )}
    </Providers>
  );
}
