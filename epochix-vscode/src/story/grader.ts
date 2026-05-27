/**
 * TypeScript port of src/epochix/story_engine/grade.py
 */

export type TaskType =
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

/** Return the letter grade for the current primary metric value. */
export function computeGrade(task: TaskType, primaryValue: number): Grade {
  const thresholds = DEFAULT_THRESHOLDS[task] ?? DEFAULT_THRESHOLDS.classification;
  const lowerBetter = LOWER_BETTER.has(task);

  for (const [grade, threshold] of thresholds) {
    if (lowerBetter) {
      if (primaryValue <= threshold) return grade;
    } else {
      if (primaryValue >= threshold) return grade;
    }
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
