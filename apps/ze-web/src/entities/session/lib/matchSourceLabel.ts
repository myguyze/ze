import type { SessionSearchResult } from "@myguyze/ze-client";

export function matchSourceLabel(source: SessionSearchResult["match_source"]): string {
  switch (source) {
    case "message":
      return "In message";
    case "summary":
      return "In summary";
    case "metadata":
      return "In title";
    default: {
      const exhaustive: never = source;
      return exhaustive;
    }
  }
}
