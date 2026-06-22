import type { ErrorObject } from "ajv";

export interface PrimitiveValidationIssue {
  path: string;
  message: string;
  keyword?: string;
}

export class PrimitiveValidationError extends Error {
  readonly path: string;
  readonly issues: readonly PrimitiveValidationIssue[];

  constructor(message: string, path: string, issues: readonly PrimitiveValidationIssue[]) {
    super(message);
    this.name = "PrimitiveValidationError";
    this.path = path;
    this.issues = issues;
  }

  static fromAjvErrors(errors: ErrorObject[] | null | undefined): PrimitiveValidationError {
    const issues = (errors ?? []).map((error) => ({
      path: formatAjvPath(error.instancePath, error.params),
      message: error.message ?? "Validation failed",
      keyword: error.keyword,
    }));
    const path = issues[0]?.path ?? "";
    const message = issues[0]?.message ?? "Invalid primitive tree";
    return new PrimitiveValidationError(message, path, issues);
  }
}

function formatAjvPath(instancePath: string, params: Record<string, unknown>): string {
  if (params.missingProperty) {
    const base = instancePath || "";
    return base ? `${base}/${String(params.missingProperty)}` : String(params.missingProperty);
  }
  return instancePath || "/";
}
