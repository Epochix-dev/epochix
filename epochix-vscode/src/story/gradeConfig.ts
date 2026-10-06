/**
 * A project's `.epochix.yaml` — a port of
 * src/epochix/story_engine/config_loader.py.
 *
 * The command line read the file (once it read it at all, in 0.7.28) and this
 * engine did not, so a workspace with custom thresholds showed one grade in
 * the panel and another from `epochix run`. The tables come from
 * grading.generated.ts; the functions are ported once and replay
 * src/test/fixtures/gradeConfig.golden.json — what the Python loader makes of
 * a set of files, which bands it then applies to which metric, and the grade
 * each gives — in gradeConfigGolden.test.ts.
 */
// The test build compiles only src/test and what it imports, so the
// declaration has to be named here to be seen from there.
// eslint-disable-next-line @typescript-eslint/triple-slash-reference
/// <reference path="../types/js-yaml.d.ts" />
import { load as loadYaml } from "js-yaml";

import { canonicalise } from "./canonical";
import {
  GOVERNED_METRICS,
  GRADE_ORDER,
  LABEL_ALIASES,
  TASK_TYPES,
  type Grade,
} from "./grading.generated";

/** Grade label (as written) to threshold. */
export type Bands = Record<string, number>;

export interface GradeConfig {
  /** Task name to its entry. */
  gradeThresholds: Record<string, Bands>;
  /** Canonical metric name to its entry. */
  metricThresholds: Record<string, Bands>;
  /** Task name to "lower is better", for a metric whose name does not say. */
  lowerBetter: Record<string, boolean>;
  /** What in the file could not be used. */
  problems: string[];
  /** The file it was read from, when it was read from one. */
  source?: string;
}

const LABELS: ReadonlySet<string> = new Set(GRADE_ORDER);
const TASK_NAMES: ReadonlySet<string> = new Set(TASK_TYPES);

// YAML 1.1's words for true and false, which PyYAML reads as booleans and
// js-yaml (YAML 1.2) leaves as strings.
const YAML_TRUE = /^(yes|Yes|YES|true|True|TRUE|on|On|ON)$/;
const YAML_FALSE = /^(no|No|NO|false|False|FALSE|off|Off|OFF)$/;
// What Python's float() accepts from a string.
const FLOAT_TEXT =
  /^[+-]?(?:\d+(?:_\d+)*\.?(?:\d+(?:_\d+)*)?(?:[eE][+-]?\d+)?|\.\d+(?:_\d+)*(?:[eE][+-]?\d+)?|inf(?:inity)?|nan)$/i;

function canonicalLabel(label: string): string {
  return LABEL_ALIASES[label.toUpperCase()] ?? label;
}

function isMapping(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Python's `float(value)`, or null where it raises. */
function toFloat(value: unknown): number | null {
  if (typeof value === "number") return value;
  if (typeof value === "boolean") return value ? 1 : 0;
  if (typeof value !== "string") return null;
  const text = value.trim();
  if (!FLOAT_TEXT.test(text)) return null;
  const lowered = text.toLowerCase().replace(/_/g, "");
  if (/^[+-]?inf(inity)?$/.test(lowered)) return lowered.startsWith("-") ? -Infinity : Infinity;
  if (/^[+-]?nan$/.test(lowered)) return NaN;
  return Number(lowered);
}

/** `bands` as [label, value], best grade first — `_ranked`. */
function ranked(bands: Bands): Array<[string, number]> {
  const canonical = new Map<string, number>();
  for (const [label, value] of Object.entries(bands)) canonical.set(canonicalLabel(label), value);
  const out: Array<[string, number]> = [];
  for (const label of GRADE_ORDER) {
    const value = canonical.get(label);
    if (value !== undefined) out.push([label, value]);
  }
  return out;
}

/**
 * Which way `bands` run, read from their own order, or null if they do not
 * say — bands_lower_better.
 */
export function bandsLowerBetter(bands: Bands): boolean | null {
  const finite = ranked(bands)
    .map(([, value]) => value)
    .filter((value) => Number.isFinite(value));
  if (finite.length < 2 || finite[0] === finite[finite.length - 1]) return null;
  return finite[0] < finite[finite.length - 1];
}

/** The usable thresholds in one entry — `_bands`. */
function readBands(key: string, gradeMap: Record<string, unknown>, problems: string[]): Bands {
  const bands: Bands = {};
  for (const [label, rawValue] of Object.entries(gradeMap)) {
    if (!LABELS.has(canonicalLabel(label))) {
      problems.push(`${key}: '${label}' is not a grade (use A+ … D, F)`);
      continue;
    }
    const value = toFloat(rawValue);
    if (value === null || Number.isNaN(value)) {
      problems.push(`${key}: the threshold for ${label} is not a number`);
      continue;
    }
    bands[label] = value;
  }
  const values = ranked(bands).map(([, value]) => value);
  const rising = values.every((v, i) => i === 0 || values[i - 1] <= v);
  const falling = values.every((v, i) => i === 0 || values[i - 1] >= v);
  if (!(rising || falling)) {
    problems.push(
      `${key}: the thresholds are not in order from A+ to F, so the entry is not used`,
    );
    return {};
  }
  return bands;
}

/** Python's `bool(flag)` on what PyYAML would have loaded. */
function toBool(flag: unknown): boolean {
  if (typeof flag === "string") {
    if (YAML_TRUE.test(flag)) return true;
    if (YAML_FALSE.test(flag)) return false;
    return flag.length > 0;
  }
  if (Array.isArray(flag)) return flag.length > 0;
  if (isMapping(flag)) return Object.keys(flag).length > 0;
  return Boolean(flag);
}

/** Whether `text` holds anything but blank lines, comments and document markers. */
function hasContent(text: string): boolean {
  return text.split("\n").some((line) => {
    const trimmed = line.trim();
    return trimmed !== "" && !trimmed.startsWith("#") && trimmed !== "---" && trimmed !== "...";
  });
}

/** The config written in `text`, or why there is none — parse_grade_config. */
export function parseGradeConfig(
  text: string,
  source?: string,
): { config: GradeConfig | null; error: string | null } {
  // A file with nothing in it — blank, every line a comment, or only a
  // document marker — sets nothing, as PyYAML reads it. That is decided here
  // rather than left to the YAML library: js-yaml 5 throws on an empty
  // document where 4 returned undefined, and the panel then called an empty
  // file "not valid YAML".
  if (!hasContent(text)) return { config: null, error: null };
  let raw: unknown;
  try {
    raw = loadYaml(text);
  } catch {
    return { config: null, error: "it is not valid YAML" };
  }
  if (raw === undefined || raw === null) return { config: null, error: null };
  if (!isMapping(raw)) return { config: null, error: "its top level is not a mapping" };

  const config: GradeConfig = {
    gradeThresholds: {},
    metricThresholds: {},
    lowerBetter: {},
    problems: [],
    source,
  };

  const thresholds = raw["grade_thresholds"];
  if (isMapping(thresholds)) {
    for (const [key, gradeMap] of Object.entries(thresholds)) {
      if (!isMapping(gradeMap)) continue;
      const bands = readBands(key, gradeMap, config.problems);
      if (Object.keys(bands).length === 0) continue;
      if (TASK_NAMES.has(key.toLowerCase())) config.gradeThresholds[key.toLowerCase()] = bands;
      else config.metricThresholds[canonicalise(key)] = bands;
    }
  }

  const lowerBetter = raw["lower_better"];
  if (isMapping(lowerBetter)) {
    for (const [task, flag] of Object.entries(lowerBetter)) config.lowerBetter[task] = toBool(flag);
  }
  return { config, error: null };
}

/**
 * The thresholds the file sets for `metric` in a run of `task`, or null —
 * GradeConfig.bands_for. An entry named after the metric wins; a task's entry
 * applies only to the metric it is written for; a `custom` entry to whatever a
 * custom run is told by.
 */
export function bandsFor(config: GradeConfig, task: string, metric: string): Bands | null {
  const own = config.metricThresholds[metric];
  if (own !== undefined && Object.keys(own).length > 0) return own;
  const entry = config.gradeThresholds[task];
  if (entry === undefined || Object.keys(entry).length === 0) return null;
  if (task === "custom" || (GOVERNED_METRICS[task] ?? []).includes(metric)) return entry;
  return null;
}

/**
 * The letter `bands` give `value` — compute_grade with custom_thresholds and
 * an explicit direction.
 */
export function gradeWithBands(bands: Bands, value: number, lowerBetter: boolean): Grade {
  const rows: Array<[Grade, number]> = Object.entries(bands).map(([label, threshold]) => [
    canonicalLabel(label) as Grade,
    threshold,
  ]);
  // Strictest first; a stable sort, as Python's is.
  rows.sort(([, a], [, b]) => {
    if (a === b) return 0;
    const ascending = a < b ? -1 : 1;
    return lowerBetter ? ascending : -ascending;
  });
  for (const [grade, threshold] of rows) {
    if (lowerBetter ? value <= threshold : value >= threshold) return grade;
  }
  return "F";
}
