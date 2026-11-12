/**
 * Whether a metric's readings can be compared one with another — a port of
 * src/epochix/story_engine/steadiness.py, where the measurements behind the
 * thresholds are written down.
 *
 * Every conclusion the engine draws sets one reading against another. A loss
 * printed per batch by a diffusion trainer moves by more between neighbours
 * than it does over the run, and supports none of them. A metric is unsteady
 * when its recent readings change direction at half the places they could AND
 * typically move by a quarter of the larger neighbour. The thresholds are
 * generated; grading.golden.json pins what Python answers.
 */
import {
  UNSTEADY_MIN_READINGS,
  UNSTEADY_STEP,
  UNSTEADY_TURN_SHARE,
  UNSTEADY_WINDOW,
} from "./grading.generated";

/** How a metric's recent readings moved. */
export interface Swing {
  /** How many were looked at. */
  readings: number;
  /** Readings at which the series changed direction. */
  turns: number;
  /** Median |change| between neighbours, as a share of the larger. */
  step: number;
}

/** The step as a sentence quotes it: a whole percentage. */
export function stepText(swing: Swing): string {
  return `${Math.floor(swing.step * 100 + 0.5)}%`;
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 1 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

/** How the last readings of `values` moved, or null with fewer than three. */
export function swing(values: readonly number[]): Swing | null {
  const recent = values.slice(-UNSTEADY_WINDOW);
  if (recent.length < 3) return null;
  let turns = 0;
  const steps: number[] = [];
  for (let i = 1; i < recent.length; i++) {
    const before = recent[i - 1];
    const here = recent[i];
    const larger = Math.max(Math.abs(before), Math.abs(here));
    steps.push(larger > 0 ? Math.abs(here - before) / larger : 0.0);
    if (i + 1 < recent.length) {
      const after = recent[i + 1];
      if ((here > before && after < here) || (here < before && after > here)) turns++;
    }
  }
  return { readings: recent.length, turns, step: median(steps) };
}

/** The swing of `values` when one reading says little about the run, else null. */
export function unsteady(values: readonly number[]): Swing | null {
  if (values.length < UNSTEADY_MIN_READINGS) return null;
  const found = swing(values);
  if (
    found !== null &&
    found.turns >= UNSTEADY_TURN_SHARE * (found.readings - 2) &&
    found.step >= UNSTEADY_STEP
  ) {
    return found;
  }
  return null;
}
