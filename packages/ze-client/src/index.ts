// Named SDK methods and all REST types — generated from the OpenAPI spec
export * from "./generated/index";

// Client factory — re-exported from the generated bundle so types align with SDK functions
export { createClient } from "./generated/client/client.gen";
export { createConfig } from "./generated/client/utils.gen";
export type { Client } from "./generated/client/types.gen";

// configure() sets the default client — no { client } needed per-call after this
// createZeClient() creates an independent client for multi-server or test use
export { configure, createZeClient } from "./client";

// WebSocket frame types — generated from Pydantic discriminated unions
export type {
  WsInboundFrame,
  WsOutboundFrame,
  WsMessageFrame,
  WsEditFrame,
  WsConfirmRequestFrame,
  WsConfirmCancelFrame,
  WsTypingFrame,
  WsTokenFrame,
  WsErrorFrame,
  WsRefreshFrame,
  WsPongFrame,
  WsSendMessageFrame,
  WsAckFrame,
  WsConfirmFrame,
  WsCommandFrame,
  WsComponentSubmitFrame,
  WsPingFrame,
  WsConfirmAction,
  WsScreenContext,
  MessageSchema,
  OnboardingMeta,
} from "./ws";

// Blob helpers — use raw fetch for binary downloads and pre-auth health checks
export { downloadExport, importArchive, healthCheck, type ImportResponse } from "./blob";

// Error class for wrapping HTTP failures from blob helpers
export { ApiError } from "./error";
