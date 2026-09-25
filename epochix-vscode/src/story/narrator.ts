/**
 * TypeScript port of src/epochix/story_engine/narrator.py
 *
 * The templates are GENERATED from the Python engine's template files, in every
 * locale it has (story/narratives.generated.ts). This module used to carry its
 * own English-only copy, so the extension told English stories whatever
 * `epochix.locale` said, in wording that had drifted from the Python engine's.
 */
import type { Phase } from "./phases";
import type { TaskType } from "./grader";
import {
  LOCALES,
  MESSAGES,
  METRIC_SPLIT_WORDS,
  NO_METRIC,
  PHASE_TEMPLATES,
  PROSE_ASSUMES,
  SPECIAL_TEMPLATES,
  type Locale,
} from "./narratives.generated";

export type { Locale };

/** A locale the templates exist for, or English. */
export function resolveLocale(locale: string | undefined): Locale {
  return (LOCALES as readonly string[]).includes(locale ?? "") ? (locale as Locale) : "en";
}

// ── Deterministic selection ───────────────────────────────────────────────────

/** Same run id, same variant — every time the run is replayed. */
function pickIndex(runId: string, n: number): number {
  // djb2 hash of the run ID
  let h = 5381;
  for (let i = 0; i < runId.length; i++) {
    h = ((h * 33) ^ runId.charCodeAt(i)) >>> 0;
  }
  return h % n;
}

function pick(variants: readonly string[], runId: string): string {
  return variants[pickIndex(runId, variants.length)];
}

// ── Public API ────────────────────────────────────────────────────────────────

export interface NarrateOptions {
  task: TaskType;
  phase: Phase;
  epoch: number | null;
  primaryValue: number;
  delta: number;
  runId: string;
  /** The series the numbers came from, e.g. "val_loss". */
  metric?: string;
  locale?: string;
}

/**
 * Whether a task's prose can honestly describe `metric`. Several task sets name
 * their metric outright ("Accuracy {value_pct}"); a log loss narrated as
 * "Accuracy 41.8%" is a false statement built from a real number. Mirrors
 * _prose_fits_metric, including its exact (case-sensitive) comparison.
 */
function proseFitsMetric(task: TaskType, metric: string | undefined): boolean {
  const assumed = PROSE_ASSUMES[task];
  if (assumed === undefined || !metric) return true;
  return assumed.has(metric);
}

/** "val_log_loss" -> "validation log loss", in the sentence's own language. */
export function displayMetric(metric: string | undefined, locale?: string): string {
  const loc = resolveLocale(locale);
  if (!metric) return NO_METRIC[loc];
  for (const [prefix, pattern] of METRIC_SPLIT_WORDS[loc]) {
    if (metric.startsWith(prefix)) {
      return pattern.replace("{}", metric.slice(prefix.length).replace(/_/g, " "));
    }
  }
  return metric.replace(/_/g, " ");
}

function fmtEpoch(epoch: number | null): string {
  return epoch !== null ? String(Math.trunc(epoch)) : "?";
}

export function narrate(opts: NarrateOptions): string {
  const loc = resolveLocale(opts.locale);
  const proseTask: TaskType = proseFitsMetric(opts.task, opts.metric) ? opts.task : "custom";
  const templates =
    PHASE_TEMPLATES[loc][`${proseTask}/${opts.phase}`] ??
    PHASE_TEMPLATES[loc][`custom/${opts.phase}`];

  const valuePct = `${(opts.primaryValue * 100).toFixed(1)}%`;
  const deltaStr = opts.delta !== 0 ? (opts.delta >= 0 ? "+" : "") + opts.delta.toFixed(4) : "0";

  return pick(templates, opts.runId)
    .replace(/\{epoch\}/g, fmtEpoch(opts.epoch))
    .replace(/\{value\}/g, opts.primaryValue.toFixed(4))
    .replace(/\{delta\}/g, deltaStr)
    .replace(/\{value_pct\}/g, valuePct)
    .replace(/\{metric\}/g, displayMetric(opts.metric, loc));
}

// ── Runs that are not progressing — mirrors narrator.py ─────────────────────
// Phase templates are chosen by how far through training a run is, not by
// whether its metric moved, so on their own they narrate progress that the
// data does not show. These replace them when the numbers say otherwise.

export function narratePastPeak(o: {
  epoch: number | null; value: number; best: number;
  bestEpoch: number | null; runId: string; locale?: string;
}): string {
  const bestAt = fmtEpoch(o.bestEpoch);
  const story = pick(SPECIAL_TEMPLATES[resolveLocale(o.locale)].pastPeak, o.runId)
    .replace(/\{epoch\}/g, fmtEpoch(o.epoch))
    .replace(/\{value\}/g, o.value.toFixed(4))
    .replace(/\{best\}/g, o.best.toFixed(4))
    .replace(/\{best_epoch\}/g, bestAt);
  return `${story} ${message("next_pastpeak", o.locale, { best_epoch: bestAt })}`;
}

export function narrateStalled(o: {
  epoch: number | null; value: number; baseline: number;
  epochsSeen: number; runId: string; locale?: string;
}): string {
  const story = pick(SPECIAL_TEMPLATES[resolveLocale(o.locale)].stalled, o.runId)
    .replace(/\{epoch\}/g, fmtEpoch(o.epoch))
    .replace(/\{value\}/g, o.value.toFixed(4))
    .replace(/\{baseline\}/g, o.baseline.toFixed(4))
    .replace(/\{epochs_seen\}/g, String(o.epochsSeen));
  return `${story} ${message("next_stalled", o.locale)}`;
}

export function narrateDiverged(o: {
  epoch: number | null; metric: string; lastValue: number;
  lastEpoch: number | null; runId: string; locale?: string;
}): string {
  const loc = resolveLocale(o.locale);
  const lastAt = fmtEpoch(o.lastEpoch);
  const story = pick(SPECIAL_TEMPLATES[loc].diverged, o.runId)
    .replace(/\{epoch\}/g, fmtEpoch(o.epoch))
    .replace(/\{last_epoch\}/g, lastAt)
    .replace(/\{value\}/g, o.lastValue.toFixed(4))
    .replace(/\{metric\}/g, displayMetric(o.metric, loc));
  return `${story} ${message("next_diverged", loc, { last_epoch: lastAt })}`;
}

/**
 * A result, not a stage of training — mirrors narrate_single_reading. A script
 * that fits once and prints a score has no arc; narrating it with the phase
 * templates described "the model awakens" for a model that had already
 * finished.
 */
export function narrateSingleReading(o: {
  value: number; metric: string; runId: string; locale?: string;
}): string {
  const loc = resolveLocale(o.locale);
  return pick(SPECIAL_TEMPLATES[loc].singleReading, o.runId)
    .replace(/\{value\}/g, o.value.toFixed(4))
    .replace(/\{metric\}/g, displayMetric(o.metric, loc));
}

/**
 * A warning or milestone message in the story's language — mirrors
 * story_engine/messages.py. These were English literals, so a Farsi or
 * French run showed English in its warning strip and timeline.
 */
export function message(
  key: string, locale: string | undefined, fields: Record<string, string> = {},
): string {
  let text = MESSAGES[resolveLocale(locale)][key] ?? MESSAGES.en[key] ?? key;
  for (const [name, value] of Object.entries(fields)) {
    text = text.split(`{${name}}`).join(value);
  }
  return text;
}

/** Every variant in every locale, so tests can assert over all of them. */
export const _VARIANTS = {
  PAST_PEAK: LOCALES.flatMap((l) => SPECIAL_TEMPLATES[l].pastPeak),
  STALLED: LOCALES.flatMap((l) => SPECIAL_TEMPLATES[l].stalled),
  DIVERGED: LOCALES.flatMap((l) => SPECIAL_TEMPLATES[l].diverged),
  SINGLE_READING: LOCALES.flatMap((l) => SPECIAL_TEMPLATES[l].singleReading),
};
