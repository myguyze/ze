import * as sdk from "./generated/sdk.gen";
import type { PluginPageResponse } from "./generated";

type SdkResult = { data?: unknown; error?: unknown };
type SdkCallable = (options?: unknown) => Promise<SdkResult>;

function getSdkFn(operationId: string): SdkCallable | undefined {
  let fn: unknown;
  try {
    fn = (sdk as Record<string, unknown>)[operationId];
  } catch {
    return undefined;
  }
  return typeof fn === "function" ? (fn as SdkCallable) : undefined;
}

function isPluginPageResponse(data: unknown): data is PluginPageResponse {
  return (
    typeof data === "object" &&
    data !== null &&
    "title" in data &&
    typeof (data as PluginPageResponse).title === "string" &&
    "tree" in data &&
    Array.isArray((data as PluginPageResponse).tree)
  );
}

export async function invokeSdkOperation(operationId: string, options?: unknown): Promise<unknown> {
  const fn = getSdkFn(operationId);
  if (!fn) {
    throw new Error(`Unknown SDK operation: ${operationId}`);
  }

  const { data, error } = await fn(options);
  if (error) {
    throw new Error(`SDK operation failed: ${operationId}`);
  }

  return data;
}

export async function loadPluginOperation(operationId: string): Promise<PluginPageResponse> {
  const data = await invokeSdkOperation(operationId);
  if (!isPluginPageResponse(data)) {
    throw new Error(`Operation ${operationId} did not return PluginPageResponse`);
  }
  return data;
}
