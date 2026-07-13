import type { WorkflowExecutionResponse } from "@myguyze/ze-client";
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

export function executionDurationMs(
  startedAt: string | null,
  completedAt: string | null,
): number | null {
  if (!startedAt || !completedAt) {
    return null;
  }
  const ms = new Date(completedAt).getTime() - new Date(startedAt).getTime();
  if (Number.isNaN(ms) || ms < 0) {
    return null;
  }
  return ms;
}

export function formatDurationMs(ms: number): string {
  if (ms < 1000) {
    return `${ms}ms`;
  }
  const seconds = ms / 1000;
  if (seconds < 60) {
    return `${seconds.toFixed(1)}s`;
  }
  const minutes = Math.floor(seconds / 60);
  const remSec = Math.round(seconds % 60);
  if (minutes < 60) {
    return remSec > 0 ? `${minutes}m ${remSec}s` : `${minutes}m`;
  }
  const hours = Math.floor(minutes / 60);
  const remMin = minutes % 60;
  return remMin > 0 ? `${hours}h ${remMin}m` : `${hours}h`;
}

export function averageSuccessfulRunDuration(
  executions: WorkflowExecutionResponse[],
): string | null {
  const durations = executions
    .filter((execution) => execution.status === "completed")
    .map((execution) => executionDurationMs(execution.started_at, execution.completed_at))
    .filter((ms): ms is number => ms !== null);

  if (durations.length === 0) {
    return null;
  }

  const avgMs = durations.reduce((sum, ms) => sum + ms, 0) / durations.length;
  return formatDurationMs(Math.round(avgMs));
}
