/**
 * TypeScript port of src/epochix/story_engine/phases.py
 */

export type Phase =
  | "awakening"
  | "learning"
  | "understanding"
  | "mastering"
  | "polishing";

export const PHASE_EMOJIS: Record<Phase, string> = {
  awakening: "🌱",
  learning: "📚",
  understanding: "💡",
  mastering: "🎯",
  polishing: "✨",
};

/**
 * Hybrid phase detector using both progress and relative metric improvement.
 *
 * @param progress      0.0–1.0 fraction of total epochs completed.
 * @param primaryValue  Current primary metric value.
 * @param baseline      Value at epoch 0 (or first recorded epoch).
 * @param target        The ideal value: 1.0 for accuracy/mAP, 0 for a loss.
 * @param lowerBetter   Whether improvement means moving DOWN towards target.
 *                      Without it a falling loss measured towards 1.0 never
 *                      counted as progress at all.
 */
export function computePhase(
  progress: number,
  primaryValue: number,
  baseline: number,
  target: number,
  lowerBetter = false,
): Phase {
  if (progress < 0.10) return "awakening";

  const span = lowerBetter ? baseline - target : target - baseline;
  const moved = lowerBetter ? baseline - primaryValue : primaryValue - baseline;
  const relative = span > 0 ? moved / (span + 1e-9) : progress;

  if (progress < 0.40 || relative < 0.40) return "learning";
  if (progress < 0.70 || relative < 0.75) return "understanding";
  if (progress < 0.95 || relative < 0.95) return "mastering";
  return "polishing";
}

/**
 * Fraction of the achievable improvement realised so far, clamped to [0, 1].
 * Mirrors relative_improvement in story_engine/phases.py; undefined when the
 * baseline already sits at the ideal, so callers can fall back.
 */
export function relativeImprovement(
  primaryValue: number,
  baseline: number,
  lowerBetter: boolean,
): number | undefined {
  const ideal = lowerBetter ? 0 : 1;
  const span = lowerBetter ? baseline - ideal : ideal - baseline;
  if (Math.abs(span) <= 1e-9) return undefined;
  const improved = lowerBetter ? baseline - primaryValue : primaryValue - baseline;
  return Math.max(0, Math.min(1, improved / span));
}

/**
 * Best-effort 0–1 progress estimate from whatever info is available.
 */
export function estimateProgress(
  currentEpoch: number | null,
  totalEpochs: number | null,
  step: number | null = null,
  totalSteps: number | null = null,
): number {
  if (currentEpoch !== null && totalEpochs !== null && totalEpochs > 0) {
    return Math.min(currentEpoch / totalEpochs, 1.0);
  }
  if (step !== null && totalSteps !== null && totalSteps > 0) {
    return Math.min(step / totalSteps, 1.0);
  }
  return 0.05; // non-zero so AWAKENING fires immediately
}
