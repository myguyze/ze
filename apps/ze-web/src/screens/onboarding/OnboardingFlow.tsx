import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowRight, Check, AlertCircle } from "lucide-react";
import { saveConfig } from "@/config/AppConfig";
import { reconnect } from "@/ws/useWebSocket";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Spotlight } from "@/lib/aceternity/spotlight";

interface OnboardingFlowProps {
  onComplete: () => void;
}

const STEPS = ["welcome", "connect", "notifications"] as const;
type Step = (typeof STEPS)[number];

export function OnboardingFlow({ onComplete }: OnboardingFlowProps) {
  const [step, setStep] = useState<Step>("welcome");
  const [serverUrl, setServerUrl] = useState("http://localhost:8000");
  const [apiKey, setApiKey] = useState("");
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<"ok" | "error" | null>(null);

  async function testConnection() {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await fetch(`${serverUrl}/api/health`, {
        headers: { Authorization: `Bearer ${apiKey}` },
      });
      setTestResult(res.ok ? "ok" : "error");
    } catch {
      setTestResult("error");
    } finally {
      setTesting(false);
    }
  }

  function handleConnect() {
    if (testResult !== "ok") return;
    saveConfig({ serverUrl, apiKey });
    reconnect();
    setStep("notifications");
  }

  const variants = {
    enter: { opacity: 0, y: 20 },
    center: { opacity: 1, y: 0 },
    exit: { opacity: 0, y: -20 },
  };

  return (
    <Spotlight className="flex h-screen items-center justify-center">
      <div className="relative w-full max-w-sm px-6">
        <AnimatePresence mode="wait">
          {step === "welcome" && (
            <motion.div
              key="welcome"
              variants={variants}
              initial="enter"
              animate="center"
              exit="exit"
              className="text-center space-y-6"
            >
              <p className="text-[64px] font-extralight tracking-tight text-white leading-none">
                Ze
              </p>
              <p className="text-sm text-[#9a9a9a] tracking-wide">
                Your personal AI assistant.
              </p>
              <Button onClick={() => setStep("connect")} className="w-full">
                Get started <ArrowRight className="w-4 h-4" />
              </Button>
            </motion.div>
          )}

          {step === "connect" && (
            <motion.div
              key="connect"
              variants={variants}
              initial="enter"
              animate="center"
              exit="exit"
              className="space-y-5"
            >
              <p className="text-xs font-semibold tracking-widest uppercase text-[#9a9a9a]">
                Connect
              </p>
              <p className="text-2xl font-extralight text-white">
                Where is Ze running?
              </p>

              <div className="space-y-3">
                <div>
                  <label className="block text-xs text-[#9a9a9a] mb-1.5 tracking-wide">
                    Server URL
                  </label>
                  <Input
                    value={serverUrl}
                    onChange={(e) => { setServerUrl(e.target.value); setTestResult(null); }}
                    placeholder="http://localhost:8000"
                  />
                </div>
                <div>
                  <label className="block text-xs text-[#9a9a9a] mb-1.5 tracking-wide">
                    API Key
                  </label>
                  <Input
                    type="password"
                    value={apiKey}
                    onChange={(e) => { setApiKey(e.target.value); setTestResult(null); }}
                    placeholder="ZE_API_KEY from your .env"
                  />
                </div>
              </div>

              <div className="flex items-center gap-3">
                <Button
                  variant="ghost"
                  onClick={testConnection}
                  disabled={testing || !serverUrl || !apiKey}
                  className="flex-1"
                >
                  {testing ? "Testing…" : "Test connection"}
                </Button>
                {testResult === "ok" && (
                  <span className="flex items-center gap-1 text-xs text-[#15846e]">
                    <Check className="w-3.5 h-3.5" /> Connected
                  </span>
                )}
                {testResult === "error" && (
                  <span className="flex items-center gap-1 text-xs text-red-400">
                    <AlertCircle className="w-3.5 h-3.5" /> Failed
                  </span>
                )}
              </div>

              <Button onClick={handleConnect} disabled={testResult !== "ok"} className="w-full">
                Continue <ArrowRight className="w-4 h-4" />
              </Button>
            </motion.div>
          )}

          {step === "notifications" && (
            <motion.div
              key="notifications"
              variants={variants}
              initial="enter"
              animate="center"
              exit="exit"
              className="space-y-5"
            >
              <p className="text-xs font-semibold tracking-widest uppercase text-[#9a9a9a]">
                Notifications
              </p>
              <p className="text-2xl font-extralight text-white">
                Stay in the loop.
              </p>
              <p className="text-sm text-[#9a9a9a] leading-relaxed">
                Install ntfy to receive push notifications when Ze has something for you.
              </p>
              <div className="flex flex-col gap-2">
                <Button
                  variant="ghost"
                  onClick={() => window.open("https://ntfy.sh", "_blank")}
                  className="w-full"
                >
                  Open ntfy
                </Button>
                <Button onClick={onComplete} className="w-full">
                  Done
                </Button>
                <button
                  onClick={onComplete}
                  className="text-xs text-[#9a9a9a] hover:text-white transition-colors py-1"
                >
                  Skip for now
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Step dots */}
        <div className="flex justify-center gap-1.5 mt-10">
          {STEPS.map((s) => (
            <span
              key={s}
              className={`w-1 h-1 rounded-full transition-all ${
                s === step ? "bg-[#8052ff] w-4" : "bg-white/20"
              }`}
            />
          ))}
        </div>
      </div>
    </Spotlight>
  );
}
