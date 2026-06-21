import { useState, useRef } from "react";
import { Check, AlertCircle } from "lucide-react";
import { getConfig, saveConfig, clearConfig } from "@/config/AppConfig";
import { reconnect } from "@/features/websocket/useWebSocket";
import { downloadExport, importArchive, createDeleteIntent, deleteData, ApiError } from "@ze/client";
import type { ImportResponse } from "@ze/client";
import { resetClient } from "@/lib/client";
import { useConnectionTest } from "@/features/settings/useConnectionTest";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function SettingsPage() {
  const cfg = getConfig();
  const [serverUrl, setServerUrl] = useState(cfg?.serverUrl ?? "");
  const [apiKey, setApiKey] = useState(cfg?.apiKey ?? "");
  const [saved, setSaved] = useState(false);

  const { testing, testResult, runTest, reset: resetTest } = useConnectionTest(serverUrl, apiKey);

  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const importInputRef = useRef<HTMLInputElement>(null);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<ImportResponse | null>(null);
  const [importError, setImportError] = useState<string | null>(null);

  const [showResetModal, setShowResetModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleteConfirmText, setDeleteConfirmText] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  function handleSave() {
    saveConfig({ serverUrl, apiKey });
    resetClient();
    reconnect();
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  function handleReset() {
    clearConfig();
    window.location.reload();
  }

  async function handleExport() {
    const current = getConfig();
    if (!current) return;
    setExporting(true);
    setExportError(null);
    try {
      await downloadExport(current.serverUrl, current.apiKey);
    } catch (e) {
      setExportError(e instanceof ApiError ? e.message : "Export failed");
    } finally {
      setExporting(false);
    }
  }

  async function handleImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const current = getConfig();
    if (!current) return;
    setImporting(true);
    setImportResult(null);
    setImportError(null);
    try {
      const result = await importArchive(current.serverUrl, current.apiKey, file);
      setImportResult(result);
    } catch (err) {
      setImportError(err instanceof ApiError ? err.message : "Import failed");
    } finally {
      setImporting(false);
      if (importInputRef.current) importInputRef.current.value = "";
    }
  }

  async function handleDelete() {
    setDeleting(true);
    setDeleteError(null);
    try {
      const { data: intent } = await createDeleteIntent();
      if (!intent) throw new Error("Failed to create delete intent");
      await deleteData({ body: { confirmation_token: intent.confirmation_token } });
      setShowDeleteModal(false);
      clearConfig();
      window.location.reload();
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : "Deletion failed");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="max-w-sm mx-auto px-4 py-8 space-y-8">
      <div>
        <p className="text-xs font-semibold tracking-widest uppercase text-smoke mb-1">Settings</p>
        <p className="text-2xl font-extralight text-white">Configuration</p>
      </div>

      <div className="space-y-4">
        <p className="text-xs font-semibold tracking-widest uppercase text-smoke">Connection</p>
        <div>
          <label className="block text-xs text-smoke mb-1.5">Server URL</label>
          <Input
            value={serverUrl}
            onChange={(e) => { setServerUrl(e.target.value); resetTest(); }}
            placeholder="http://localhost:8000"
          />
        </div>
        <div>
          <label className="block text-xs text-smoke mb-1.5">API Key</label>
          <Input
            type="password"
            value={apiKey}
            onChange={(e) => { setApiKey(e.target.value); resetTest(); }}
            placeholder="ZE_API_KEY"
          />
        </div>

        <div className="flex items-center gap-3">
          <Button variant="ghost" onClick={runTest} disabled={testing} className="flex-1">
            {testing ? "Testing…" : "Test"}
          </Button>
          {testResult === "ok" && (
            <span className="flex items-center gap-1 text-xs text-lichen">
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
        <p className="text-xs font-semibold tracking-widest uppercase text-smoke">Notifications</p>
        <p className="text-sm text-smoke leading-relaxed">
          Ze uses ntfy for push notifications. Install the ntfy app and subscribe to your topic.
        </p>
        <Button variant="ghost" onClick={() => window.open("https://ntfy.sh", "_blank")} className="w-full">
          Open ntfy
        </Button>
      </div>

      <div className="space-y-3 pt-4 border-t border-white/10">
        <p className="text-xs font-semibold tracking-widest uppercase text-smoke">Your data</p>
        <p className="text-sm text-smoke leading-relaxed">
          Export a full archive of your personal data, or permanently delete everything Ze knows about you.
        </p>
        <Button variant="ghost" onClick={handleExport} disabled={exporting} className="w-full">
          {exporting ? "Preparing export…" : "Export your data"}
        </Button>
        {exportError && <p className="text-xs text-red-400">{exportError}</p>}

        <input ref={importInputRef} type="file" accept=".zip" className="hidden" onChange={handleImport} />
        <Button
          variant="ghost"
          onClick={() => { setImportResult(null); setImportError(null); importInputRef.current?.click(); }}
          disabled={importing}
          className="w-full"
        >
          {importing ? "Importing…" : "Import data"}
        </Button>
        {importResult && (
          <p className="text-xs text-lichen">
            Imported {importResult.domains_imported.length} domains
            ({Object.values(importResult.rows_imported).reduce((a, b) => a + b, 0)} rows).
          </p>
        )}
        {importError && <p className="text-xs text-red-400">{importError}</p>}

        <Button
          variant="danger"
          onClick={() => { setShowDeleteModal(true); setDeleteConfirmText(""); setDeleteError(null); }}
          className="w-full"
        >
          Delete all data
        </Button>
      </div>

      <div className="pt-4 border-t border-white/10">
        <Button variant="danger" onClick={() => setShowResetModal(true)} className="w-full">
          Reset configuration
        </Button>
      </div>

      {showResetModal && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 px-4">
          <div className="bg-[#111] border border-white/20 rounded-xl p-6 w-full max-w-sm space-y-5">
            <div>
              <p className="text-lg font-semibold text-white">Reset configuration?</p>
              <p className="text-sm text-smoke mt-1 leading-relaxed">
                This removes the saved server URL and API key. Ze will show the setup screen.
              </p>
            </div>
            <div className="flex gap-3">
              <Button variant="ghost" onClick={() => setShowResetModal(false)} className="flex-1">
                Cancel
              </Button>
              <Button variant="danger" onClick={handleReset} className="flex-1">
                Reset
              </Button>
            </div>
          </div>
        </div>
      )}

      {showDeleteModal && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 px-4">
          <div className="bg-[#111] border border-red-900/40 rounded-xl p-6 w-full max-w-sm space-y-5">
            <div>
              <p className="text-lg font-semibold text-white">Delete all data?</p>
              <p className="text-xs text-red-400 mt-0.5 font-medium uppercase tracking-widest">
                This cannot be undone
              </p>
            </div>

            <ul className="text-sm text-smoke space-y-1">
              {[
                "Memories, facts and episodes",
                "Goals and milestones",
                "Contacts",
                "Messages and conversation history",
                "Reminders",
                "Usage history",
              ].map((item) => (
                <li key={item} className="flex items-center gap-2">
                  <span className="w-1 h-1 rounded-full bg-red-500/60 flex-shrink-0" />
                  {item}
                </li>
              ))}
            </ul>

            <div className="border-t border-white/10 pt-4">
              <p className="text-xs text-smoke mb-2">Want a copy first?</p>
              <Button variant="ghost" onClick={handleExport} disabled={exporting} className="w-full text-sm">
                {exporting ? "Preparing export…" : "Export your data first"}
              </Button>
            </div>

            <div>
              <label className="block text-xs text-smoke mb-1.5">
                Type <span className="text-white font-mono">DELETE</span> to confirm
              </label>
              <Input
                value={deleteConfirmText}
                onChange={(e) => setDeleteConfirmText(e.target.value)}
                placeholder="DELETE"
                autoFocus
              />
            </div>

            {deleteError && <p className="text-xs text-red-400">{deleteError}</p>}

            <div className="flex gap-3">
              <Button
                variant="ghost"
                onClick={() => setShowDeleteModal(false)}
                disabled={deleting}
                className="flex-1"
              >
                Cancel
              </Button>
              <Button
                variant="danger"
                onClick={handleDelete}
                disabled={deleteConfirmText !== "DELETE" || deleting}
                className="flex-1"
              >
                {deleting ? "Deleting…" : "Delete everything"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
