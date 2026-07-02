export interface SnippetPart {
  text: string;
  highlight: boolean;
}

export function parseSearchSnippet(snippet: string): SnippetPart[] {
  const parts: SnippetPart[] = [];
  const regex = /<b>(.*?)<\/b>|([^<]+)/g;
  let match: RegExpExecArray | null = regex.exec(snippet);
  while (match !== null) {
    if (match[1] !== undefined) {
      parts.push({ text: match[1], highlight: true });
    } else if (match[2]) {
      parts.push({ text: match[2], highlight: false });
    }
    match = regex.exec(snippet);
  }
  if (parts.length === 0 && snippet) {
    parts.push({ text: snippet, highlight: false });
  }
  return parts;
}
