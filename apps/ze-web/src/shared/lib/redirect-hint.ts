/** Build a route path with a redirect-hint hash target. */
export function redirectHintPath(path: string, hintId: string): string {
  const base = path.startsWith("/") ? path : `/${path}`;
  return `${base}#${hintId}`;
}

/** How long the destination highlight stays visible. */
export const REDIRECT_HINT_DURATION_MS = 2200;
