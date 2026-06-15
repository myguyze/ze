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
};

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
