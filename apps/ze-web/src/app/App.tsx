import { useEffect, useState } from "react";
import { RouterProvider } from "react-router-dom";
import { bootstrapWs } from "@/app/bootstrap-ws";
import { Providers } from "@/app/providers";
import { router } from "@/app/router";
import { OnboardingWizard } from "@/widgets/onboarding-wizard";
import { startWs } from "@/shared/api";
import { hasConfig } from "@/shared/config";

bootstrapWs();

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
        <OnboardingWizard onComplete={handleOnboardingComplete} />
      ) : (
        <RouterProvider router={router} />
      )}
    </Providers>
  );
}
