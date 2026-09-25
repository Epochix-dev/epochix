/**
 * TypeScript port of src/epochix/story_engine/grade.py
 */

export type TaskType =
  | "segmentation"
  | "classification"
  | "detection"
  | "regression"
  | "biometric"
  | "gaze"
  | "nlp"
  | "generative"
  | "custom";

export type Grade =
  | "A+" | "A" | "A-"
  | "B+" | "B" | "B-"
  | "C+" | "C" | "C-"
  | "D" | "F" | "I";

type Threshold = [Grade, number];

const DEFAULT_THRESHOLDS: Record<TaskType, Threshold[]> = {
  // Mirrors _DEFAULT_THRESHOLDS in src/epochix/story_engine/grade.py.
  // IoU is a stricter scale than accuracy: 0.75 IoU is strong where 0.75
  // accuracy is mediocre, so the bands sit lower.
  segmentation: [
    ["A+", 0.85], ["A", 0.78], ["A-", 0.72], ["B+", 0.66], ["B", 0.60],
    ["B-", 0.54], ["C+", 0.47], ["C", 0.40], ["C-", 0.32], ["D", 0.20],
  ],
  classification: [
    ["A+", 0.95], ["A", 0.90], ["A-", 0.87],
    ["B+", 0.82], ["B", 0.75], ["B-", 0.70],
    ["C+", 0.65], ["C", 0.60], ["C-", 0.55],
    ["D", 0.50], ["F", 0.0],
  ],
  detection: [
    ["A+", 0.75], ["A", 0.65], ["A-", 0.58],
    ["B+", 0.50], ["B", 0.42], ["B-", 0.35],
    ["C+", 0.28], ["C", 0.20], ["C-", 0.15],
    ["D", 0.08], ["F", 0.0],
  ],
  nlp: [
    // Perplexity: lower = better. Thresholds are MAXIMUM values.
    ["A+", 10.0], ["A", 20.0], ["A-", 30.0],
    ["B+", 50.0], ["B", 80.0], ["B-", 120.0],
    ["C+", 180.0], ["C", 250.0], ["C-", 350.0],
    ["D", 500.0], ["F", Infinity],
  ],
  biometric: [
    // EER: lower = better
    ["A+", 0.01], ["A", 0.03], ["A-", 0.05],
    ["B+", 0.08], ["B", 0.10], ["B-", 0.15],
    ["C+", 0.20], ["C", 0.25], ["C-", 0.30],
    ["D", 0.40], ["F", Infinity],
  ],
  gaze: [
    // MAE in degrees: lower = better
    ["A+", 0.5], ["A", 1.0], ["A-", 1.5],
    ["B+", 2.5], ["B", 4.0], ["B-", 6.0],
    ["C+", 9.0], ["C", 12.0], ["C-", 16.0],
    ["D", 22.0], ["F", Infinity],
  ],
  regression: [
    // Generic MAE: lower = better
    ["A+", 0.01], ["A", 0.05], ["A-", 0.10],
    ["B+", 0.20], ["B", 0.35], ["B-", 0.50],
    ["C+", 0.70], ["C", 1.00], ["C-", 1.50],
    ["D", 2.50], ["F", Infinity],
  ],
  generative: [
    // Treat as classification-like (FID / quality score)
    ["A+", 0.95], ["A", 0.90], ["A-", 0.87],
    ["B+", 0.82], ["B", 0.75], ["B-", 0.70],
    ["C+", 0.65], ["C", 0.60], ["C-", 0.55],
    ["D", 0.50], ["F", 0.0],
  ],
  custom: [
    ["A+", 0.95], ["A", 0.90], ["A-", 0.87],
    ["B+", 0.82], ["B", 0.75], ["B-", 0.70],
    ["C+", 0.65], ["C", 0.60], ["C-", 0.55],
    ["D", 0.50], ["F", 0.0],
  ],
};

const LOWER_BETTER = new Set<TaskType>(["nlp", "biometric", "gaze", "regression"]);

/**
 * Bands belonging to a METRIC rather than a task — mirrors _METRIC_THRESHOLDS
 * in story_engine/grade.py.
 *
 * The regression row above is an MAE band set, and MAE carries the target's
 * units, so it graded a model with R² 0.996 as F purely because the targets
 * were large. R² is the one regression metric with a scale of its own.
 */
const METRIC_THRESHOLDS: Record<string, Threshold[]> = {
  R2: [
    ["A+", 0.95], ["A", 0.90], ["A-", 0.85],
    ["B+", 0.80], ["B", 0.70], ["B-", 0.60],
    ["C+", 0.50], ["C", 0.40], ["C-", 0.30],
    ["D", 0.10], ["F", -Infinity],
  ],
};
METRIC_THRESHOLDS["val_R2"] = METRIC_THRESHOLDS["R2"];

/** Whether a metric can be graded without knowing the dataset's units. */
export function hasAbsoluteScale(metric: string | undefined): boolean {
  return metric !== undefined && metric in METRIC_THRESHOLDS;
}

/** Return the letter grade for the current primary metric value. */
export function computeGrade(
  task: TaskType,
  primaryValue: number,
  metric?: string,
): Grade {
  const metricBands = metric === undefined ? undefined : METRIC_THRESHOLDS[metric];
  const thresholds =
    metricBands ?? DEFAULT_THRESHOLDS[task] ?? DEFAULT_THRESHOLDS.classification;
  // A metric with its own bands brings its own direction too: regression is a
  // lower-is-better task, so grading R² by the task direction scores a perfect
  // fit as F.
  const lowerBetter = metricBands ? false : LOWER_BETTER.has(task);

  for (const [grade, threshold] of thresholds) {
    if (lowerBetter) {
      if (primaryValue <= threshold) return grade;
    } else {
      if (primaryValue >= threshold) return grade;
    }
  }
  return "F";
}

// ── Metric direction — mirrors metric_lower_better in story_engine/grade.py ──
//
// A metric whose direction is unknown falls back to its TASK's default, and
// the failure is silent: the grade simply comes out inverted. Exact keys are
// checked before the substring hints because the hints get some names
// backwards ("val_mape" contains "map", a higher-is-better hint).
const DIRECTION_BY_KEY: Record<string, boolean> = {
  mape: true, smape: true, wer: true, cer: true, bpc: true, lpips: true,
  nll: true, log_loss: true, val_log_loss: true, logloss: true,
  rouge: false, val_rouge: false, rouge1: false, rouge2: false, rougel: false,
  meteor: false, val_meteor: false,
  tar: false, val_tar: false, far: true, val_far: true,
  tar_at_far_0_001: false, val_tar_at_far_0_001: false,
  fid: true, val_fid: true, kid: true, val_kid: true,
  is_score: false, inception_score: false, spearman: false, pearson: false,
  error_rate: true, val_error_rate: true,
  val_mae: true, val_rmse: true, val_mse: true, val_mape: true,
  val_medae: true, val_rmsle: true,
  val_r2: false, val_auc: false, val_f1: false, val_accuracy: false,
  brier: true, huber: true, quantile_loss: true, medae: true, rmsle: true,
  ndcg: false, mrr: false, specificity: false, sensitivity: false,
  pixel_accuracy: false, top5_accuracy: false, balanced_accuracy: false,
  mcc: false, kappa: false, explained_variance: false, silhouette: false,
  // LightGBM's names for MAE / MSE. No hint matches "l1" or "l2", so without a
  // pin they inherited the task default and a falling error graded as decline.
  l1: true, l2: true, val_l1: true, val_l2: true, train_l1: true, train_l2: true,
};
const LOWER_NAME_HINTS = [
  "loss", "error", "err", "mae", "mse", "rmse", "perplexity", "ppl", "eer", "nll",
];
const HIGHER_NAME_HINTS = [
  "acc", "accuracy", "f1", "auc", "map", "precision", "recall", "iou", "dice",
  "bleu", "psnr", "ssim", "r2",
];

/** Direction inferred from a metric's name, or undefined when it says nothing. */
export function metricLowerBetter(metric: string | undefined): boolean | undefined {
  if (!metric) return undefined;
  const n = metric.toLowerCase();
  if (n in DIRECTION_BY_KEY) return DIRECTION_BY_KEY[n];
  if (LOWER_NAME_HINTS.some((h) => n.includes(h))) return true;
  if (HIGHER_NAME_HINTS.some((h) => n.includes(h))) return false;
  return undefined;
}

/** The task's default direction, used only when the metric's name says nothing. */
export function taskLowerBetter(task: TaskType): boolean {
  return LOWER_BETTER.has(task);
}

// ── Grading on improvement — mirrors grade_by_trajectory in grade.py ────────
//
// For a metric with no absolute scale (a bare loss, a log loss, FID) there is
// no "an 0.19 loss is a B": the number only means something relative to where
// it started. Grading such a run against accuracy bands scored a healthy,
// falling loss as if it were 19% accuracy. Sorted best-first; the value is the
// minimum fraction of improvement from the baseline for that grade.
const TRAJECTORY_THRESHOLDS: Threshold[] = [
  ["A+", 0.70], ["A", 0.55], ["A-", 0.45], ["B+", 0.35], ["B", 0.25],
  ["B-", 0.16], ["C+", 0.09], ["C", 0.04], ["C-", 0.005],
  ["D", -0.03], // essentially flat
  // anything worse — the metric moved the wrong way — is an F
];

export function gradeByTrajectory(
  baseline: number,
  current: number,
  lowerBetter: boolean,
): Grade {
  const denom = Math.abs(baseline) > 1e-9 ? Math.abs(baseline) : 1e-9;
  const improvement = lowerBetter
    ? (baseline - current) / denom
    : (current - baseline) / denom;
  for (const [grade, threshold] of TRAJECTORY_THRESHOLDS) {
    if (improvement >= threshold) return grade;
  }
  return "F";
}

/** Return grade colour hex (matches frontend theme). */
export function gradeColor(grade: Grade): string {
  if (grade.startsWith("A")) return "#22c55e"; // green
  if (grade.startsWith("B")) return "#3b82f6"; // blue
  if (grade.startsWith("C")) return "#f59e0b"; // amber
  if (grade === "D") return "#f97316"; // orange
  return "#ef4444"; // red for F / I
}

// Below this many readings of the primary metric a letter is provisional.
// Mirrors FEW_READINGS in story_engine/grade.py.
export const FEW_READINGS = 5;

/**
 * Why a letter deserves less weight than it looks, or null — mirrors
 * story_engine.grade.grade_note. An 11-epoch run and a 200-epoch run received
 * equally confident letters; a letter resting on few readings, or taken while
 * the metric was still setting new bests, is provisional and now says so.
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
