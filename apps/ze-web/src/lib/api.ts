import { getConfig } from "@/config/AppConfig";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const cfg = getConfig();
  if (!cfg) throw new ApiError(401, "Not configured");

  const res = await fetch(`${cfg.serverUrl}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${cfg.apiKey}`,
      ...init?.headers,
    },
  });

  if (!res.ok) {
    throw new ApiError(res.status, await res.text());
  }

  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body) }),
  delete: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "DELETE", body: JSON.stringify(body) }),
};

export async function downloadExport(serverUrl: string, apiKey: string): Promise<void> {
  const res = await fetch(`${serverUrl}/api/data/export`, {
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

export interface DeleteIntent {
  confirmation_token: string;
  expires_at: string;
}

export interface ImportResult {
  domains_imported: string[];
  rows_imported: Record<string, number>;
}

export async function importArchive(
  serverUrl: string,
  apiKey: string,
  file: File,
): Promise<ImportResult> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${serverUrl}/api/data/import`, {
    method: "POST",
    headers: { Authorization: `Bearer ${apiKey}` },
    body: form,
  });
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return res.json() as Promise<ImportResult>;
}

/** Test reachability of an arbitrary server before credentials are saved. */
export async function healthCheck(serverUrl: string, apiKey: string): Promise<boolean> {
  try {
    const res = await fetch(`${serverUrl}/api/health`, {
      headers: { Authorization: `Bearer ${apiKey}` },
    });
    return res.ok;
  } catch {
    return false;
  }
}
