import { useState } from "react";
import { Check, AlertCircle } from "lucide-react";
import { getConfig, saveConfig, clearConfig } from "@/config/AppConfig";
import { reconnect } from "@/ws/useWebSocket";
import { healthCheck } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function SettingsScreen() {
  const cfg = getConfig();
  const [serverUrl, setServerUrl] = useState(cfg?.serverUrl ?? "");
  const [apiKey, setApiKey] = useState(cfg?.apiKey ?? "");
  const [saved, setSaved] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<"ok" | "error" | null>(null);

  async function testConnection() {
    setTesting(true);
    setTestResult(null);
    try {
      const ok = await healthCheck(serverUrl, apiKey);
      setTestResult(ok ? "ok" : "error");
    } finally {
      setTesting(false);
    }
  }

  function handleSave() {
    saveConfig({ serverUrl, apiKey });
    reconnect();
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  function handleReset() {
    if (!confirm("Reset all settings? You will need to reconfigure Ze.")) return;
    clearConfig();
    window.location.reload();
  }

  return (
    <div className="max-w-sm mx-auto px-4 py-8 space-y-8">
      <div>
        <p className="text-xs font-semibold tracking-widest uppercase text-[#9a9a9a] mb-1">
          Settings
        </p>
        <p className="text-2xl font-extralight text-white">Configuration</p>
      </div>

      <div className="space-y-4">
        <p className="text-xs font-semibold tracking-widest uppercase text-[#9a9a9a]">
          Connection
        </p>
        <div>
          <label className="block text-xs text-[#9a9a9a] mb-1.5">Server URL</label>
          <Input
            value={serverUrl}
            onChange={(e) => { setServerUrl(e.target.value); setTestResult(null); }}
            placeholder="http://localhost:8000"
          />
        </div>
        <div>
          <label className="block text-xs text-[#9a9a9a] mb-1.5">API Key</label>
          <Input
            type="password"
            value={apiKey}
            onChange={(e) => { setApiKey(e.target.value); setTestResult(null); }}
            placeholder="ZE_API_KEY"
          />
        </div>

        <div className="flex items-center gap-3">
          <Button variant="ghost" onClick={testConnection} disabled={testing} className="flex-1">
            {testing ? "Testing…" : "Test"}
          </Button>
          {testResult === "ok" && (
            <span className="flex items-center gap-1 text-xs text-[#15846e]">
              <Check className="w-3.5 h-3.5" /> OK
            </span>
          )}
          {testResult === "error" && (
            <span className="flex items-center gap-1 text-xs text-red-400">
              <AlertCircle className="w-3.5 h-3.5" /> Failed
            </span>
          )}
        </div>

        <Button onClick={handleSave} className="w-full">
          {saved ? "Saved ✓" : "Save & reconnect"}
        </Button>
      </div>

      <div className="space-y-3 pt-4 border-t border-white/10">
        <p className="text-xs font-semibold tracking-widest uppercase text-[#9a9a9a]">
          Notifications
        </p>
        <p className="text-sm text-[#9a9a9a] leading-relaxed">
          Ze uses ntfy for push notifications. Install the ntfy app and subscribe to your topic.
        </p>
        <Button
          variant="ghost"
          onClick={() => window.open("https://ntfy.sh", "_blank")}
          className="w-full"
        >
          Open ntfy
        </Button>
      </div>

      <div className="pt-4 border-t border-white/10">
        <Button variant="danger" onClick={handleReset} className="w-full">
          Reset configuration
        </Button>
      </div>
    </div>
  );
}
