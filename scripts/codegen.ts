#!/usr/bin/env bun
/**
 * Generates TypeScript types for @ze/client from the Python backend.
 *
 * Usage:
 *   bun run scripts/codegen.ts
 *
 * Schemas are extracted directly from Python (no server needed).
 *
 * REST types: @hey-api/openapi-ts → sdk.gen.ts + types.gen.ts + client.gen.ts
 * WebSocket types: json-schema-to-typescript → ws.ts
 */

import { execSync, execFileSync } from "child_process";
import { mkdirSync, writeFileSync, unlinkSync } from "fs";
import { join } from "path";
import { compile } from "json-schema-to-typescript";

const root = join(import.meta.dir, "..");
const generatedDir = join(root, "packages/ze-client/src/generated");
const tmpSchema = join(root, "packages/ze-client/src/generated/.openapi.tmp.json");

mkdirSync(generatedDir, { recursive: true });

// ── 1. REST SDK from OpenAPI ─────────────────────────────────────────────────

console.log("Extracting OpenAPI schema from Python...");

const openapiJson = execSync(
  `cd ${root} && uv run --project apps/ze-api python -c "` +
    `import json; from ze_api.api.app import app; print(json.dumps(app.openapi()))"`,
  { encoding: "utf8" },
);

writeFileSync(tmpSchema, openapiJson);

console.log("Generating REST SDK (@hey-api/openapi-ts)...");

execSync(
  `cd ${root} && bunx openapi-ts -i ${tmpSchema} -o packages/ze-client/src/generated --client @hey-api/client-fetch --silent`,
  { stdio: "inherit" },
);

console.log("  → packages/ze-client/src/generated/ (sdk.gen.ts, types.gen.ts, client.gen.ts)");

try {
  unlinkSync(tmpSchema);
} catch {
  // ignore
}

// ── 2. WebSocket types from Pydantic ─────────────────────────────────────────

console.log("Extracting WebSocket schemas from Python...");

const wsSchemaJson = execSync(
  `cd ${root} && uv run --project apps/ze-api python -c "` +
    `import json; from pydantic import TypeAdapter; ` +
    `from ze_api.api.schemas import WsInboundFrame, WsOutboundFrame; ` +
    `inbound = TypeAdapter(WsInboundFrame).json_schema(); ` +
    `outbound = TypeAdapter(WsOutboundFrame).json_schema(); ` +
    `defs = {**inbound.pop('\\$defs', {}), **outbound.pop('\\$defs', {})}; ` +
    `defs['WsInboundFrame'] = inbound; defs['WsOutboundFrame'] = outbound; ` +
    `print(json.dumps({'\\$defs': defs, 'title': 'WsProtocol', 'type': 'object', ` +
    `'properties': {'inbound': {'\\$ref': '#/\\$defs/WsInboundFrame'}, 'outbound': {'\\$ref': '#/\\$defs/WsOutboundFrame'}}}))"`,
  { encoding: "utf8" },
);

const wsSchema = JSON.parse(wsSchemaJson) as Parameters<typeof compile>[0];

console.log("Generating WebSocket types (json-schema-to-typescript)...");

const wsTs = await compile(wsSchema, "WsProtocol", {
  bannerComment: "",
  additionalProperties: false,
  unreachableDefinitions: true,
  format: true,
});

writeFileSync(join(generatedDir, "ws.ts"), wsTs);
console.log("  → packages/ze-client/src/generated/ws.ts");

console.log("\nCodegen complete.");
