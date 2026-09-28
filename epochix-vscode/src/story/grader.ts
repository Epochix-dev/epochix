/**
 * Grading and metric direction — a line-for-line port of
 * src/epochix/story_engine/grade.py.
 *
 * Every table and threshold comes from grading.generated.ts, which
 * scripts/gen_ts_engine_tables.py writes from the Python engine; nothing here
 * is a copied number. The functions are ported once, and
 * src/test/fixtures/grading.golden.json — Python's answers for a sweep of
 * inputs across every band edge, direction name and grade note — is replayed
 * against them by gradingGolden.test.ts, so a drift fails a test instead of
 * shipping. These were hand-ported before, and had drifted.
 */
import {
  DEFAULT_THRESHOLDS,
  DIRECTION_BY_KEY,
  FEW_READINGS,
  GRADE_ORDER,
  HIGHER_NAME_HINTS,
  LOWER_BETTER_TASKS,
  LOWER_NAME_HINTS,
  METRIC_THRESHOLDS,
  TRAJECTORY_THRESHOLDS,
  type Grade,
  type TaskType,
} from "./grading.generated";

export type { Grade, TaskType };
export { FEW_READINGS, GRADE_ORDER };

/** Whether a metric can be graded without knowing the dataset's units. */
export function hasAbsoluteScale(metric: string | undefined): boolean {
  return metric !== undefined && metric !== "" && metric in METRIC_THRESHOLDS;
}

/** The task's default direction, used only when the metric's name says nothing. */
export function taskLowerBetter(task: TaskType): boolean {
  return LOWER_BETTER_TASKS.has(task);
}

/** Direction inferred from a metric's name, or undefined when it says nothing. */
export function metricLowerBetter(metric: string | undefined | null): boolean | undefined {
  if (!metric) return undefined;
  const n = metric.toLowerCase();
  // Exact match first: substring hints are a heuristic and get some names
  // backwards ("val_mape" contains "map"), which silently inverts the grade.
  if (Object.prototype.hasOwnProperty.call(DIRECTION_BY_KEY, n)) return DIRECTION_BY_KEY[n];
  if (LOWER_NAME_HINTS.some((h) => n.includes(h))) return true;
  if (HIGHER_NAME_HINTS.some((h) => n.includes(h))) return false;
  return undefined;
}

/**
 * The letter for a value — compute_grade. A metric with bands of its own (R²)
 * brings its own direction: regression is a lower-is-better task, and grading
 * R² by the task's direction scored a perfect fit as F.
 */
export function computeGrade(task: TaskType, primaryValue: number, metric?: string | null): Grade {
  let thresholds = DEFAULT_THRESHOLDS[task] ?? DEFAULT_THRESHOLDS.classification;
  let lowerBetter = LOWER_BETTER_TASKS.has(task);
  const metricBands = metric ? METRIC_THRESHOLDS[metric] : undefined;
  if (metricBands !== undefined) {
    thresholds = metricBands;
    const nameDir = metricLowerBetter(metric);
    if (nameDir !== undefined) lowerBetter = nameDir;
  }
  for (const [grade, threshold] of thresholds) {
    if (lowerBetter ? primaryValue <= threshold : primaryValue >= threshold) return grade;
  }
  return "F";
}

/**
 * Grade a metric with no absolute scale by how far it improved —
 * grade_by_trajectory. A bare loss means nothing except relative to where it
 * started; one that got worse earns an F.
 */
export function gradeByTrajectory(baseline: number, current: number, lowerBetter: boolean): Grade {
  const denom = Math.abs(baseline) > 1e-9 ? Math.abs(baseline) : 1e-9;
  const improvement = lowerBetter ? (baseline - current) / denom : (current - baseline) / denom;
  for (const [grade, threshold] of TRAJECTORY_THRESHOLDS) {
    if (improvement >= threshold) return grade;
  }
  return "F";
}

/**
 * Why a letter deserves less weight than it looks, or null — grade_note. A
 * letter resting on few readings, or taken while the metric was still setting
 * new bests, is provisional and says so.
 */
export function gradeNote(
  grade: Grade,
  readings: number,
  o: { hasEpoch: boolean; newBest: boolean },
): "few_readings" | "still_improving" | null {
  if (grade === "I") return null;
  if (!o.hasEpoch && readings <= 1) return null;
  if (readings < FEW_READINGS) return "few_readings";
  if (o.newBest) return "still_improving";
  return null;
}

/** Higher is better; I (incomplete) ranks below everything. */
export function gradeRank(grade: Grade): number {
  const i = GRADE_ORDER.indexOf(grade);
  return i < 0 ? -1 : GRADE_ORDER.length - i;
}

/** Return grade colour hex (matches frontend theme). */
export function gradeColor(grade: Grade): string {
  if (grade.startsWith("A")) return "#22c55e"; // green
  if (grade.startsWith("B")) return "#3b82f6"; // blue
  if (grade.startsWith("C")) return "#f59e0b"; // amber
  if (grade === "D") return "#f97316"; // orange
  return "#ef4444"; // red for F / I
}
