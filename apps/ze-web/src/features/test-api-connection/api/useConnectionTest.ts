import { healthCheck } from "@myguyze/ze-client";
import { useState } from "react";

export function useConnectionTest(serverUrl: string, apiKey: string) {
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<"ok" | "error" | null>(null);

  async function runTest() {
    setTesting(true);
    setTestResult(null);
    try {
      const ok = await healthCheck(serverUrl, apiKey);
      setTestResult(ok ? "ok" : "error");
    } finally {
      setTesting(false);
    }
  }

  function reset() {
    setTestResult(null);
  }

  return { testing, testResult, runTest, reset };
}
