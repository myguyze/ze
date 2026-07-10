export function relativeTime(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function startOfDay(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}

/** Buckets an item's ISO date into a human day-group label ("Today", "Yesterday", "This week", or a calendar date). */
export function dayGroupLabel(dateStr: string): string {
  const date = new Date(dateStr);
  const today = startOfDay(new Date());
  const day = startOfDay(date);
  const daysAgo = Math.round((today - day) / 86_400_000);

  if (daysAgo <= 0) return "Today";
  if (daysAgo === 1) return "Yesterday";
  if (daysAgo < 7) return "This week";
  if (daysAgo < 30) return "This month";
  return date.toLocaleDateString("en-US", { month: "long", year: "numeric" });
}
