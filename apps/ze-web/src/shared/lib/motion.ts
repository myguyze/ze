/**
 * Centralized motion tokens — use these instead of raw Tailwind transition classes
 * so that timing is consistent across the app.
 *
 *   motion.colors  — hover colour/border tints        (150ms)
 *   motion.base    — panels, buttons, general UI      (200ms)
 *   motion.fade    — opacity fades                    (200ms)
 *   motion.slide   — transform + opacity combos       (250ms)
 *   motion.accordion — height-driven expand/collapse  (200ms, grid trick)
 */
export const motion = {
  colors:    "transition-colors duration-150 ease-out",
  base:      "transition-all duration-200 ease-out",
  fade:      "transition-opacity duration-200 ease-out",
  rotate:    "transition-transform duration-200 ease-out",
  slide:     "transition-[transform,opacity] duration-250 ease-out",
  accordion: "transition-[grid-template-rows,opacity] duration-200 ease-out",
} as const;
