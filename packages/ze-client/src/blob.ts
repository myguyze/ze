import type { ImportResponse } from "./generated/types.gen";
import { ApiError } from "./error";

export type { ImportResponse };

export async function downloadExport(serverUrl: string, apiKey: string): Promise<void> {
  const res = await fetch(`${serverUrl}/api/v0/data/export`, {
    headers: { Authorization: `Bearer ${apiKey}` },
  });
  if (!res.ok) throw new ApiError(res.status, await res.text());
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  const ts = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
  a.href = url;
  a.download = `ze-export-${ts}.zip`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export async function importArchive(
  serverUrl: string,
  apiKey: string,
  file: File,
): Promise<ImportResponse> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${serverUrl}/api/v0/data/import`, {
    method: "POST",
    headers: { Authorization: `Bearer ${apiKey}` },
    body: form,
  });
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return res.json() as Promise<ImportResponse>;
}

export async function healthCheck(serverUrl: string, apiKey: string): Promise<boolean> {
  try {
    const res = await fetch(`${serverUrl}/api/v0/health`, {
      headers: { Authorization: `Bearer ${apiKey}` },
    });
    return res.ok;
  } catch {
    return false;
  }
}
