export function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"] as const;
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** i;
  const digits = i === 0 ? 0 : value < 10 ? 1 : 0;
  return `${value.toFixed(digits)} ${units[i]}`;
}

export function formatCount(n: number | null): string {
  if (n === null) return "—";
  return n.toLocaleString();
}

export function domainPrefix(name: string): string {
  return name.includes(".") ? name.split(".")[0] : name;
}

export function shortDomainName(name: string): string {
  return name.includes(".") ? name.split(".").slice(1).join(".") : name;
}

export function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}
