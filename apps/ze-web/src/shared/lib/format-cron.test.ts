import { describe, it, expect } from "vitest";
import { formatCronExpression } from "@/shared/lib/format-cron";

describe("formatCronExpression", () => {
  it("formats daily schedules with day context", () => {
    expect(formatCronExpression("0 8 * * *")).toBe("At 08:00 AM, every day");
  });

  it("formats weekday schedules", () => {
    expect(formatCronExpression("0 8 * * 1")).toBe("At 08:00 AM, only on Monday");
  });

  it("formats interval schedules", () => {
    expect(formatCronExpression("*/30 * * * *")).toBe("Every 30 minutes");
    expect(formatCronExpression("*/5 * * * *")).toBe("Every 5 minutes");
  });

  it("formats weekly midnight schedules", () => {
    expect(formatCronExpression("0 0 * * 0")).toBe("At 12:00 AM, only on Sunday");
  });

  it("trims whitespace before parsing", () => {
    expect(formatCronExpression("  0 8 * * *  ")).toBe("At 08:00 AM, every day");
  });

  it("returns the original expression when parsing fails", () => {
    expect(formatCronExpression("not a cron")).toBe("not a cron");
  });
});
