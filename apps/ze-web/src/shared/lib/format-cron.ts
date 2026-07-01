import cronstrue from "cronstrue";

const DAILY_AT_TIME = /^(\d+|\d+-\d+) (\d+|\d+-\d+) \* \* \*$/;

export function formatCronExpression(expression: string): string {
  const trimmed = expression.trim();
  if (!trimmed) {
    return trimmed;
  }

  try {
    return cronstrue.toString(trimmed, {
      use24HourTimeFormat: false,
      verbose: DAILY_AT_TIME.test(trimmed),
      throwExceptionOnParseError: true,
    });
  } catch {
    return trimmed;
  }
}
