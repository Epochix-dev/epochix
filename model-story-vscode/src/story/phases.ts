/**
 * TypeScript port of src/model_story/story_engine/phases.py
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
 * @param target        Theoretical maximum (1.0 for accuracy/mAP, etc.).
 */
export function computePhase(
  progress: number,
  primaryValue: number,
  baseline: number,
  target: number,
): Phase {
  if (progress < 0.10) return "awakening";

  const span = target - baseline;
  const relative =
    span > 0 ? (primaryValue - baseline) / (span + 1e-9) : progress;

  if (progress < 0.40 || relative < 0.40) return "learning";
  if (progress < 0.70 || relative < 0.75) return "understanding";
  if (progress < 0.95 || relative < 0.95) return "mastering";
  return "polishing";
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
