import { formatCronExpression } from "@/shared/lib/format-cron";

export function formatSchedule(schedule: string | null): string {
  if (!schedule) {
    return "Manual";
  }
  return formatCronExpression(schedule);
}

export function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
