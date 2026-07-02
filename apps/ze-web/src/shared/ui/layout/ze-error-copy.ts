const ZE_ERROR_HEADLINES = [
  "Something went sideways in my circuits.",
  "I hit a snag I didn't anticipate.",
  "Well. That wasn't in the plan.",
  "My neurons tripped over each other.",
  "I ran into an unexpected state.",
  "That didn't go how I expected.",
] as const;

const ZE_ERROR_SUBTEXTS = [
  "Not ideal, but fixable — want to try again?",
  "Give me another shot and we'll pick up where we left off.",
  "These things happen. A refresh usually clears it.",
  "Happens to the best of us. Let's reset and continue.",
  "I'm still here — just need a clean slate.",
  "No panic. Reload and we'll get back on track.",
] as const;

export function pickZeErrorCopy(seed = 0): { headline: string; subtext: string } {
  const index = Math.abs(seed) % ZE_ERROR_HEADLINES.length;
  return {
    headline: ZE_ERROR_HEADLINES[index]!,
    subtext: ZE_ERROR_SUBTEXTS[index]!,
  };
}

export function seedFromError(error: Error | undefined): number {
  if (!error?.message) return Date.now();
  let hash = 0;
  for (let i = 0; i < error.message.length; i += 1) {
    hash = (hash * 31 + error.message.charCodeAt(i)) | 0;
  }
  return hash;
}
