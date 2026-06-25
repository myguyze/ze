import { importArchive, ApiError } from "@ze/client";
import type { ImportResponse } from "@ze/client";
import { useRef, useState, type ChangeEvent } from "react";
import { getConfig } from "@/shared/config";

export function useImportUserData() {
  const importInputRef = useRef<HTMLInputElement>(null);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<ImportResponse | null>(null);
  const [importError, setImportError] = useState<string | null>(null);

  async function importData(e: ChangeEvent<HTMLInputElement>) {
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

  function openImportDialog() {
    setImportResult(null);
    setImportError(null);
    importInputRef.current?.click();
  }

  return {
    importing,
    importResult,
    importError,
    importData,
    importInputRef,
    openImportDialog,
  };
}
