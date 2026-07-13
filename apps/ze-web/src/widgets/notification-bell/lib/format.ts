export function relativeTime(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

/** Route for a notification's deep link target, or null if it has none / isn't navigable. */
export function targetRoute(targetType: string | null, targetId: string | null): string | null {
  if (!targetType || !targetId) return null;
  if (targetType === "goal" || targetType === "goal_suggestion") return `/goals/${targetId}`;
  if (targetType === "workflow_run") return `/workflows/${targetId}`;
  return null;
}
