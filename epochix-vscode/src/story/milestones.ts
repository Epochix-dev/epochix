/**
 * Milestones — a line-for-line port of src/epochix/story_engine/milestones.py.
 *
 * The extension's engine had its own set ("first reading", grade changes,
 * phase changes) that the Python engine never raised, and none of Python's:
 * the same log showed one list of milestones in VS Code and another in the
 * browser and in every report. The thresholds and metric sets come from
 * grading.generated.ts; tests/fixtures/corpus_truth.json pins each log's
 * milestones for both engines.
 */
import { MILESTONE_THRESHOLDS, NOT_A_FRACTION, UNIT_BOUNDED_METRICS } from "./grading.generated";
import { message, type Counter } from "./narrator";
import { fixed } from "./pyFormat";

/** A milestone, shaped like the Python model's (models.Milestone). */
export interface Milestone {
  seq: number;
  kind: string;
  epoch: number | null;
  value: number | null;
  message: string;
}

function isFraction(metric: string | null): boolean {
  return metric !== null && UNIT_BOUNDED_METRICS.has(metric) && !NOT_A_FRACTION.has(metric);
}

export class MilestoneTracker {
  private _best = -Infinity;
  private readonly _crossed = new Set<number>();
  private readonly _fired = new Set<string>();
  /** [gain, seq, epoch] of each reading against the one before it. */
  private _deltas: [number, number, number | null][] = [];
  private _metric: string | null = null;

  constructor(private readonly _locale: string) {}

  /**
   * The milestones a reading of the story's metric reaches. The direction is
   * the metric's own, as the engine decided it — never the task's.
   */
  check(
    epoch: number | null,
    seq: number,
    value: number,
    prev: number | null,
    metric: string,
    lowerBetter: boolean,
  ): Milestone[] {
    const fired: Milestone[] = [];

    // Best, deltas and thresholds belong to one metric: across a switch they
    // would compare a loss with an accuracy.
    const switched = metric !== this._metric;
    if (switched) {
      this._metric = metric;
      this._best = -Infinity;
      this._crossed.clear();
      this._deltas = [];
    }

    const isBest = lowerBetter
      ? this._best === -Infinity || value < this._best
      : value > this._best;
    if (isBest) {
      if (!this._fired.has("best_so_far")) {
        fired.push({
          seq, kind: "best_so_far", epoch, value,
          message: message("ms_best", this._locale, { value: fixed(value, 4) }),
        });
        this._fired.add("best_so_far");
      }
      this._best = value;
    }

    // "Crossed N%" only for a metric that IS a fraction of its maximum, read
    // the right way up and on its 0-1 scale.
    if (!lowerBetter && isFraction(metric) && value >= 0 && value <= 1) {
      for (const threshold of MILESTONE_THRESHOLDS) {
        const pct = String(Math.trunc(threshold * 100));
        const kind = `first_above_${pct}`;
        if (value >= threshold && !this._crossed.has(threshold) && !this._fired.has(kind)) {
          this._crossed.add(threshold);
          this._fired.add(kind);
          fired.push({
            seq, kind, epoch, value,
            message: message("ms_crossed", this._locale, { pct, value: fixed(value, 4) }),
          });
        }
      }
    }

    // Improvements only: the largest step the wrong way is not one.
    if (prev !== null && !switched) {
      this._deltas.push([lowerBetter ? prev - value : value - prev, seq, epoch]);
    }
    return fired;
  }

  /**
   * The milestones a run ends with. The biggest jump is only known at the
   * end, but it carries the seq and epoch of the reading where it happened;
   * of equal gains, the first. `counter` is what the run counts by: the
   * biggest "single-epoch" improvement of a boosting run was a reading's.
   */
  finalize(seq: number, epoch: number | null, counter: Counter | null = null): Milestone[] {
    const result: Milestone[] = [];
    let best: [number, number, number | null] | null = null;
    for (const d of this._deltas) if (best === null || d[0] > best[0]) best = d;
    if (best !== null && best[0] > 0 && !this._fired.has("biggest_jump")) {
      const [gain, jumpSeq, jumpEpoch] = best;
      this._fired.add("biggest_jump");
      result.push({
        seq: jumpSeq, kind: "biggest_jump", epoch: jumpEpoch, value: gain,
        message: message("ms_biggest_jump", this._locale, { value: fixed(gain, 4) }, counter),
      });
    }
    result.push({
      seq: seq + 1,
      kind: "training_complete",
      epoch,
      value: this._best === -Infinity ? null : this._best,
      message: message("ms_complete", this._locale),
    });
    return result;
  }
}
