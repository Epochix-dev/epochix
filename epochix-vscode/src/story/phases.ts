/**
 * Training phases — a line-for-line port of src/epochix/story_engine/phases.py.
 *
 * The bars come from grading.generated.ts (generated from the Python engine)
 * and grading.golden.json pins Python's answers, replayed by
 * gradingGolden.test.ts. The hand-ported version had drifted: it did not clamp
 * the improvement ratio, fell back to the clock on a negative span, and
 * answered a made-up 0.05 of progress when the run's length was unknown.
 */
import { AWAKENING_BELOW, PHASE_STEPS, type Phase } from "./grading.generated";

export type { Phase };

export const PHASE_EMOJIS: Record<Phase, string> = {
  awakening: "🌱",
  learning: "📚",
  understanding: "💡",
  mastering: "🎯",
  polishing: "✨",
};

/**
 * Fraction of the achievable improvement realised so far, in [0, 1] —
 * relative_improvement. For a higher-is-better metric the ideal defaults to 1,
 * for a lower-is-better one to 0. Null when the span is degenerate (the
 * baseline already at the ideal), so callers can fall back.
 */
export function relativeImprovement(
  primaryValue: number,
  baseline: number,
  lowerBetter: boolean,
  ideal: number | null = null,
): number | null {
  const target = ideal ?? (lowerBetter ? 0.0 : 1.0);
  const span = lowerBetter ? baseline - target : target - baseline;
  if (Math.abs(span) <= 1e-9) return null;
  const improved = lowerBetter ? baseline - primaryValue : primaryValue - baseline;
  return Math.max(0.0, Math.min(1.0, improved / span));
}

/**
 * Hybrid phase detector — compute_phase. `progress` is the fraction of
 * training completed, or null when the run's length is unknown; then the
 * advancement is the relative improvement alone.
 */
export function computePhase(
  progress: number | null,
  primaryValue: number,
  baseline: number,
  lowerBetter = false,
  ideal: number | null = null,
): Phase {
  const rel = relativeImprovement(primaryValue, baseline, lowerBetter, ideal);
  // When the metric span is degenerate, lean on the clock (or 0 if unknown).
  const relative = rel !== null ? rel : progress !== null ? progress : 0.0;
  // Advancement = the clock when there is one, else metric-driven progress.
  const adv = progress !== null ? progress : relative;

  if (adv < AWAKENING_BELOW) return "awakening";
  for (const [phase, advBar, relBar] of PHASE_STEPS) {
    if (adv < advBar || relative < relBar) return phase;
  }
  return "polishing";
}

/**
 * Best-effort 0–1 progress fraction, or null when it cannot be known —
 * estimate_progress. Null, not a made-up constant, so the phase advances on
 * real improvement instead of pretending the run is stuck at its start.
 */
export function estimateProgress(
  currentEpoch: number | null,
  totalEpochs: number | null,
  step: number | null = null,
  totalSteps: number | null = null,
): number | null {
  if (currentEpoch !== null && totalEpochs && totalEpochs > 0) {
    return Math.min(currentEpoch / totalEpochs, 1.0);
  }
  if (step !== null && totalSteps && totalSteps > 0) {
    return Math.min(step / totalSteps, 1.0);
  }
  return null;
}
