import { downloadExport, ApiError } from "@myguyze/ze-client";
import { useState } from "react";
import { getConfig } from "@/shared/config";

export function useExportUserData() {
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  async function exportData() {
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

  return { exporting, exportError, exportData };
}
