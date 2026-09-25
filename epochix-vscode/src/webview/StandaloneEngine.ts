/**
 * StandaloneEngine
 *
 * Orchestrates the TypeScript parser → story pipeline for standalone mode
 * (no Python sidecar).  Mirrors the high-level logic of pipeline.py.
 */
import type { Parser, ParserContext, RawMetric } from "../parsers/base";
import { makeContext } from "../parsers/base";
import { PytorchLightningParser } from "../parsers/pytorchLightning";
import { KerasParser } from "../parsers/keras";
import { HuggingFaceParser } from "../parsers/huggingface";
import { YoloParser } from "../parsers/yolo";
import { UniversalParser } from "../parsers/universal";
import { BoostingParser } from "../parsers/boosting";
import type { Phase } from "../story/phases";
import {
  computePhase,
  estimateProgress,
  relativeImprovement,
} from "../story/phases";
import type { Grade, TaskType } from "../story/grader";
import {
  computeGrade,
  gradeByTrajectory,
  hasAbsoluteScale,
  metricLowerBetter,
  taskLowerBetter,
} from "../story/grader";
import {
  narrate,
  narrateDiverged,
  narratePastPeak,
  narrateSingleReading,
  narrateStalled,
  message,
  displayMetric,
  resolveLocale,
  type Locale,
} from "../story/narrator";
import { NEVER_METRICS } from "../parsers/neverMetrics";
import type { StoryFrameMsg, MilestoneMsg, WarningMsg, RunSummaryMsg } from "./messages";
import { parseArchitecture, type ArchLayer } from "../story/architecture";
import {
  CANONICAL_MAP,
  ON_SCALE,
  PREFERRED_KEYS,
  SPLIT_PREFIXES,
  TASK_SIGNALS,
  UNIT_SUFFIXES,
  VALIDATION_PREFIXES,
} from "../story/engineTables.generated";

// ── Canonical key normalisation ───────────────────────────────────────────────
//
// The tables are GENERATED from the Python engine (story/engineTables.generated.ts)
// and this is Python's canonicalize_key, step for step. Both used to be ported by
// hand: a differential run found 170 of 319 names canonicalised differently —
// `valid_loss` and `eval_loss` became TRAINING loss here, and `val_mae` merged
// into training MAE, so the same log got a different primary metric and grade
// depending on which engine read it.

function stripUnits(key: string): string {
  for (const suffix of UNIT_SUFFIXES) {
    if (key.endsWith(suffix) && key.length > suffix.length) return key.slice(0, -suffix.length);
  }
  return key;
}

/**
 * Canonical name for a raw metric key. Unlike Python, which files every
 * unknown key under "custom", an unknown key keeps its own name: this engine
 * narrates a custom run by the metric it actually logged.
 */
function canonicalise(key: string): string {
  const k = key.toLowerCase().trim();
  const direct = CANONICAL_MAP.get(k);
  if (direct !== undefined) return direct;
  const base = CANONICAL_MAP.get(stripUnits(k));
  if (base !== undefined) return base;
  for (const pre of SPLIT_PREFIXES) {
    if (k.startsWith(pre)) {
      const rest = stripUnits(k.slice(pre.length));
      const held = VALIDATION_PREFIXES.has(pre) ? CANONICAL_MAP.get(`val_${rest}`) : undefined;
      if (held !== undefined) return held;
      const plain = CANONICAL_MAP.get(rest);
      if (plain !== undefined) return plain;
      break;
    }
  }
  return key;
}

// ── Task detection ────────────────────────────────────────────────────────────

// Nothing distinguishes a gaze model from any other regression except its
// names. Mirrors refine_gaze: classifying every MAE run as gaze graded a
// house-price MAE against bands built for angles in degrees.
const GAZE_HINT = /gaze|angular|pitch|yaw|eye_|_eye\b|fixation/i;

function detectTask(metrics: readonly RawMetric[]): TaskType {
  // First match wins, a run matching nothing is CUSTOM — as in Python.
  const keys = new Set(metrics.map((m) => canonicalise(m.key)));
  for (const [task, signals] of TASK_SIGNALS) {
    if ([...signals].some((s) => keys.has(s))) {
      if (task === "regression" && metrics.some((m) => GAZE_HINT.test(m.key))) {
        return "gaze";
      }
      return task;
    }
  }
  return "custom";
}

// A metric explicitly assigned a non-number: `loss: nan`, `val_loss=inf`.
// Mirrors _NON_FINITE_ASSIGNMENT in pipeline.py. Bounded quantifier: an
// unbounded `\w+` before a delimiter is O(n^2) on a long line.
const NON_FINITE_ASSIGNMENT =
  /\b([A-Za-z_]\w{0,63})\s*[:=]\s*[-+]?(?:nan|inf(?:inity)?)\b/i;

// Pathology thresholds, mirroring story_engine/warnings.py.
const OVERFIT_WINDOW = 3;
const PLATEAU_WINDOW = 5;
const PLATEAU_DELTA = 0.01;
const DIVERGE_GROWTH = 10;
// Stalled / past-peak, mirroring story_engine/__init__.py.
const PAST_PEAK_REL_DROP = 0.01;
const STALL_MIN_EPOCHS = 3;
const STALL_REL_IMPROVEMENT = 0.03;

// Logged beside the metrics but never a measure of the model.
const AUXILIARY = /^(lr|learning_rate|epoch|step|steps|iter|iteration|time|eta|it_s|samples_per_second|grad_norm)$/i;

/**
 * The key this run should be narrated by: the task's first preferred key that
 * was actually logged, compared case-insensitively because canonical names are
 * mixed case ("mIoU") while logs are not. A CUSTOM run with none of them takes
 * the first real metric it logged, by its real name.
 */
function primaryMetricFrom(
  task: TaskType,
  seen: ReadonlyArray<string>,
): string {
  const byLower = new Map<string, string>();
  for (const k of seen) if (!byLower.has(k.toLowerCase())) byLower.set(k.toLowerCase(), k);
  for (const key of PREFERRED_KEYS[task]) {
    const hit = byLower.get(key.toLowerCase());
    if (hit !== undefined) return hit;
  }
  const real = seen.find((k) => !NEVER_METRICS.has(k.toLowerCase()) && !AUXILIARY.test(k));
  return real ?? primaryMetricFor(task);
}

function primaryMetricFor(task: TaskType): string {
  switch (task) {
    case "detection": return "mAP50";
    case "nlp": return "perplexity";
    case "biometric": return "EER";
    case "gaze": return "MAE";
    case "segmentation": return "mIoU";
    case "regression": return "MAE";
    case "custom": return "val_loss";
    default: return "val_accuracy";
  }
}

// ── Engine ────────────────────────────────────────────────────────────────────

// Pick a parser the moment one recognises the format, and stop waiting for a
// confident answer after this many lines. The bar is 0.45 because that is what
// Keras scores on a `verbose=2` run — no ASCII progress bar, just "Epoch 1/5"
// followed by "100/100 - 2s - loss: …", which is what every redirected or
// non-TTY run prints. Universal floors at 0.10 and is always kept as a
// fallback alongside the winner, so an early pick is never fatal.
const CONFIDENT_SNIFF = 0.45;
// If nothing has recognised the format by now it is a plain key=value log, and
// universal will handle it — stop holding output back. Kept small because a
// LIVE run must start drawing during training, not only when it ends.
const MAX_SNIFF_LINES = 6;

// Metrics needed before the task can be classified. Everything parsed before
// that is banked and replayed, so no epoch is lost to the warmup.
const TASK_MIN_METRICS = 4;

interface WarmupLine {
  metrics: RawMetric[];
  epoch: number | null;
  totalEpochs: number | null;
}

// A model summary is printed once at the top of a run; scanning further is
// wasted work and unbounded memory.
const _ARCH_SCAN_LINES = 200;

export class StandaloneEngine {
  private readonly _parsers: Parser[];
  private _activeParsers: Parser[] | null = null;
  private _pending: string[] = [];
  private _warmup: WarmupLine[] = [];
  private _taskDetected = false;
  private _ctx: ParserContext = makeContext();

  private _runId = generateId();
  private _task: TaskType = "classification";
  private _primaryMetric = "val_accuracy";
  private _baseline: number | null = null;
  private _lastPrimary = 0;
  private _primaryReadings = 0;
  private _best: number | null = null;
  private _bestEpoch: number | null = null;
  // Set once, at the first `key: nan`. A MetricEvent-style value cannot carry
  // NaN (the parsers will not read it), so the raw line is checked instead.
  private _diverged = false;
  // Inputs to the pathology checks, mirroring story_engine/warnings.py.
  private _trainLosses: number[] = [];
  private _valLosses: number[] = [];
  private _bestTrainLoss: number | null = null;
  private _trainSeen = 0;
  private _allMetrics: RawMetric[] = [];
  private _frames: StoryFrameMsg[] = [];
  private _milestones: MilestoneMsg[] = [];
  private _warnings: WarningMsg[] = [];
  private _seenMilestones = new Set<string>();
  private _buffer = "";
  // Lines kept only long enough to look for a model summary. A summary is
  // printed once, at the top, so a bounded window is enough and a long run
  // cannot grow this without limit.
  private _archScan: string[] = [];
  private _architecture: ArchLayer[] = [];

  // A task the user pinned (`epochix.taskHint`). Detection runs after the
  // first few metrics and used to overwrite it, so the setting did nothing.
  private readonly _taskHint: TaskType | undefined;

  // The language the story is told in (`epochix.locale`). The engine used to
  // have English templates only, whatever the setting said.
  private readonly _locale: Locale;

  constructor(taskHint?: TaskType, locale?: string) {
    this._taskHint = taskHint;
    this._locale = resolveLocale(locale);
    this._parsers = [
      new PytorchLightningParser(),
      new KerasParser(),
      new HuggingFaceParser(),
      new YoloParser(),
      new BoostingParser(),
      new UniversalParser(),
    ].sort((a, b) => b.priority - a.priority);

    if (taskHint) {
      this._task = taskHint;
      this._primaryMetric = primaryMetricFor(taskHint);
    }
  }

  /** Feed a chunk of text (may contain multiple lines). Returns new frames. */
  feed(text: string): StoryFrameMsg[] {
    this._buffer += text;
    const newFrames: StoryFrameMsg[] = [];

    // Process complete lines
    const lines = this._buffer.split(/\r?\n/);
    this._buffer = lines.pop() ?? "";

    // A model summary is printed once, at the top. Scan a bounded window for
    // one and stop as soon as it is found.
    if (this._archScan.length < _ARCH_SCAN_LINES) {
      for (const ln of lines) {
        if (this._archScan.length >= _ARCH_SCAN_LINES) break;
        this._archScan.push(ln);
      }
      // Keep the LONGEST parse rather than latching on the first success. A
      // summary arrives one line at a time, so the first successful parse sees
      // exactly one layer — latching there reported a single-layer model for an
      // eight-layer network.
      const found = parseArchitecture(this._archScan);
      if (found.length > this._architecture.length) this._architecture = found;
      if (this._archScan.length >= _ARCH_SCAN_LINES) this._archScan = [];
    }

    for (const line of lines) {
      if (this._activeParsers === null) {
        // Hold the line while we work out the format. It used to be DISCARDED
        // (`if (seq < 50) return []`), so a run shorter than 50 lines rendered
        // an empty dashboard, and the sniff then ran on an empty sample — which
        // meant only the universal parser was ever selected.
        this._pending.push(line);
        if (!this._trySelectParsers()) continue;

        const backlog = this._pending;
        this._pending = [];
        for (const held of backlog) newFrames.push(...this._processLine(held));
        continue;
      }
      newFrames.push(...this._processLine(line));
    }
    return newFrames;
  }

  /**
   * Commit whatever is still held: a run can end before we ever reached a
   * confident sniff (a short, format-ambiguous log). Without this its lines
   * would sit in _pending forever and the dashboard would stay empty.
   */
  flush(): StoryFrameMsg[] {
    const newFrames: StoryFrameMsg[] = [];

    if (this._buffer.length > 0) {
      const last = this._buffer;
      this._buffer = "";
      if (this._activeParsers === null) this._pending.push(last);
      else newFrames.push(...this._processLine(last));
    }

    if (this._activeParsers === null && this._pending.length > 0) {
      this._activeParsers = this._selectParsers(this._pending);
      const backlog = this._pending;
      this._pending = [];
      for (const held of backlog) newFrames.push(...this._processLine(held));
    }

    newFrames.push(...this._drainWarmup(true));
    return newFrames;
  }

  /** Finish the run; returns a summary. */
  finish(): RunSummaryMsg | null {
    if (this._frames.length === 0) return null;
    const last = this._frames[this._frames.length - 1];
    return {
      id: this._runId,
      name: null,
      taskType: this._task,
      finalGrade: last.grade,
      storySummary: last.narrative,
    };
  }

  /** Layers detected from a model summary, or an empty list. */
  architecture(): ArchLayer[] {
    return this._architecture;
  }

  /**
   * Raw metric events, shaped like the server's `/api/metrics` payload.
   *
   * The dashboard's diagnostics, metric-spread, histogram and learning-rate
   * panels all read `store.metrics`, and the extension never sent any — so
   * without the Python package those panels read "Diagnostics appear once
   * metrics arrive…" forever, including on the bundled demo.
   */
  /**
   * The metric the frames actually measure.
   *
   * The server must be told this at run creation: its default is `val_loss`,
   * and a run whose frames carry accuracy but whose `primary_metric` says
   * loss makes the learning curve invert the line — a rising model drawn as
   * a falling one.
   */
  primaryMetricKey(): string {
    return this._primaryMetric;
  }

  metrics(): { canonical_key: string; epoch: number | null; value: number }[] {
    return this._allMetrics.map((m) => ({
      canonical_key: canonicalise(m.key),
      epoch: m.epoch,
      value: m.value,
    }));
  }

  snapshot(): StoryFrameMsg[] {
    return [...this._frames];
  }

  milestones(): MilestoneMsg[] {
    return [...this._milestones];
  }

  warnings(): WarningMsg[] {
    return [...this._warnings];
  }

  /** Scrub to a specific sequence number (no-op in standalone; UI handles it). */
  scrubTo(_seq: number): void {
    // UI-only operation
  }

  // ── Private ──────────────────────────────────────────────────────────────────

  /**
   * Pick parsers as soon as one is confident, or once the sample is big enough
   * to stop waiting. Returns true when a selection was made.
   */
  private _trySelectParsers(): boolean {
    const scores = this._parsers.map((p) => ({
      parser: p,
      score: p.sniff(this._pending),
    }));
    scores.sort((a, b) => b.score - a.score);

    if (scores[0].score < CONFIDENT_SNIFF && this._pending.length < MAX_SNIFF_LINES) {
      return false;
    }
    this._activeParsers = this._selectParsers(this._pending);
    return true;
  }

  /** Parse one line and turn it into a frame (or bank it during warmup). */
  private _processLine(line: string): StoryFrameMsg[] {
    this._ctx.seq++;
    const metrics = this._activeParsers!.flatMap((p) =>
      p.parseLine(line, this._ctx),
    );
    this._allMetrics.push(...metrics);
    for (const m of metrics) {
      const key = canonicalise(m.key);
      if (key === "train_loss") this._trainLosses.push(m.value);
      else if (key === "val_loss") this._valLosses.push(m.value);
    }

    // `loss: nan` never reaches the parsers — none of them reads a non-number —
    // so a diverged run's story simply stopped at its last finite epoch and kept
    // the grade it had earned before blowing up. Checked on the raw line,
    // requiring `:` or `=` so prose ("info", "inf batches") cannot trip it.
    const nonFinite = NON_FINITE_ASSIGNMENT.exec(line);
    if (nonFinite !== null && !this._diverged) {
      const out: StoryFrameMsg[] = [];
      if (!this._taskDetected) out.push(...this._drainWarmup(true));
      const frame = this._divergenceFrame(canonicalise(nonFinite[1]), this._ctx.currentEpoch);
      if (frame !== null) out.push(this._emit(frame));
      return out;
    }

    if (!this._taskDetected) {
      if (metrics.length > 0) {
        // Snapshot the epoch: these frames are built later, by which time the
        // parser context has moved on to a different epoch.
        this._warmup.push({
          metrics,
          epoch: this._ctx.currentEpoch,
          totalEpochs: this._ctx.totalEpochs,
        });
      }
      // `=== 10` used to mean a log emitting 3 metrics per line counted
      // 3,6,9,12 and NEVER hit it — so the task was never detected and not one
      // frame was ever built.
      if (this._allMetrics.length >= TASK_MIN_METRICS) {
        return this._drainWarmup(false);
      }
      return [];
    }

    const frame = this._buildFrame(
      metrics,
      this._ctx.currentEpoch,
      this._ctx.totalEpochs,
    );
    return frame ? [this._emit(frame)] : [];
  }

  /**
   * Detect the task from what we've seen, then replay every banked warmup line
   * so the epochs that arrived *before* detection still reach the dashboard.
   */
  private _drainWarmup(force: boolean): StoryFrameMsg[] {
    if (this._taskDetected) return [];
    if (this._allMetrics.length === 0) return [];
    if (!force && this._allMetrics.length < TASK_MIN_METRICS) return [];

    this._task = this._taskHint ?? detectTask(this._allMetrics);
    this._primaryMetric = primaryMetricFrom(
      this._task,
      [...new Set(this._allMetrics.map((m) => canonicalise(m.key)))],
    );
    this._taskDetected = true;

    const out: StoryFrameMsg[] = [];
    for (const held of this._warmup) {
      const frame = this._buildFrame(held.metrics, held.epoch, held.totalEpochs);
      if (frame) out.push(this._emit(frame));
    }
    this._warmup = [];
    return out;
  }

  private _emit(frame: StoryFrameMsg): StoryFrameMsg {
    this._frames.push(frame);
    this._checkMilestones(frame);
    this._checkWarnings();
    return frame;
  }

  private _selectParsers(sampleLines: readonly string[]): Parser[] {
    const scores = this._parsers.map((p) => ({
      parser: p,
      score: p.sniff(sampleLines),
    }));
    scores.sort((a, b) => b.score - a.score);
    // Keep top parser plus universal
    const best = scores[0];
    const universal = this._parsers.find((p) => p.name === "universal")!;
    if (best.parser.name === "universal") return [universal];
    // A boosting row is read whole by its own parser. Universal alongside it
    // re-read the same row with its collapsed keys — a duplicate `logloss`
    // series, and CatBoost's derived `best` column charted as a metric.
    if (best.parser.name === "boosting") return [best.parser];
    return [best.parser, universal];
  }

  private _buildFrame(
    metrics: RawMetric[],
    epoch: number | null,
    totalEpochs: number | null,
  ): StoryFrameMsg | null {
    const primaryMetrics = metrics.filter(
      (m) => canonicalise(m.key) === this._primaryMetric,
    );
    if (primaryMetrics.length === 0) return null;

    const primary = primaryMetrics[primaryMetrics.length - 1];
    const value = primary.value;
    const key = this._primaryMetric;

    if (this._baseline === null) this._baseline = value;
    const delta = value - this._lastPrimary;
    this._lastPrimary = value;
    this._primaryReadings++;

    // Direction from the metric's own name first: the task default is right
    // for the task's headline metric and silently inverts every other one.
    const lowerBetter = metricLowerBetter(key) ?? taskLowerBetter(this._task);

    // Best so far, updated BEFORE the past-peak check, as in the Python engine.
    if (this._best === null || (lowerBetter ? value < this._best : value > this._best)) {
      this._best = value;
      this._bestEpoch = epoch;
    }

    const rel = relativeImprovement(value, this._baseline, lowerBetter);
    // Honest advancement, as in the Python engine: the clock when the total
    // length is known, otherwise the fraction of achievable improvement
    // realised. estimateProgress answers a constant 0.05 when there is no
    // total, which pinned every such run — boosting rounds, `epoch 3 loss=…`
    // logs — in its first phase for its whole life: "the model is processing
    // its first examples at epoch 55".
    const progress = totalEpochs !== null && totalEpochs > 0
      ? estimateProgress(epoch, totalEpochs)
      : (rel ?? 0);
    const phase: Phase = computePhase(
      progress, value, this._baseline, lowerBetter ? 0 : 1.0, lowerBetter,
    );
    const grade = this._grade(value, lowerBetter);

    let pastPeak = false;
    if (Math.abs(this._best) > 1e-9) {
      const drop = (lowerBetter ? value - this._best : this._best - value) / Math.abs(this._best);
      pastPeak = drop > PAST_PEAK_REL_DROP;
    }
    // Stalled means FLAT. A run that got worse clears "less than 3% improvement"
    // exactly as a flat one does, and was told it was "not learning yet".
    const stalled =
      this._primaryReadings >= STALL_MIN_EPOCHS &&
      rel !== undefined &&
      rel < STALL_REL_IMPROVEMENT &&
      !pastPeak;

    let narrative: string;
    // A result, not a stage of training: one reading and no epoch is a script
    // that fit once and printed a score. Mirrors narrate_single_reading.
    if (epoch === null && this._primaryReadings <= 1) {
      narrative = narrateSingleReading({
        value, metric: key, runId: this._runId, locale: this._locale,
      });
    } else if (stalled) {
      narrative = narrateStalled({
        epoch, value, baseline: this._baseline,
        epochsSeen: this._primaryReadings, runId: this._runId, locale: this._locale,
      });
    } else if (pastPeak) {
      narrative = narratePastPeak({
        epoch, value, best: this._best, bestEpoch: this._bestEpoch, runId: this._runId,
        locale: this._locale,
      });
    } else {
      narrative = narrate({
        task: this._task,
        phase,
        epoch,
        primaryValue: value,
        delta,
        runId: this._runId,
        metric: key,
        locale: this._locale,
      });
    }

    return {
      runId: this._runId,
      seq: this._ctx.seq,
      epoch,
      progress,
      phase,
      grade,
      primaryMetricValue: value,
      confidence: primary.confidence,
      narrative,
      taskType: this._task,
    };
  }

  /**
   * Mirrors the grading branch of StoryEngine._emit: a task's absolute bands
   * apply only to its on-scale metric; anything else is graded on how far it
   * improved, and with a single reading there is nothing to measure against.
   */
  private _grade(value: number, lowerBetter: boolean): Grade {
    const key = this._primaryMetric;
    const onScale = [...ON_SCALE[this._task]].some((k) => k.toLowerCase() === key.toLowerCase());
    if (onScale || hasAbsoluteScale(key)) {
      return computeGrade(this._task, value, key);
    }
    if (this._baseline !== null && this._primaryReadings >= 2) {
      return gradeByTrajectory(this._baseline, value, lowerBetter);
    }
    // One reading of a metric with no known scale: anything else is a guess
    // dressed as a verdict.
    return "I";
  }

  /**
   * The frame that closes a run whose metric became NaN: grade F, a divergence
   * warning, and the LAST REAL epoch and value — dating it to the NaN epoch
   * would assert a measurement that does not exist. Null when nothing finite
   * was ever read, since there is then no honest number to show.
   */
  private _divergenceFrame(metric: string, epoch: number | null): StoryFrameMsg | null {
    this._diverged = true;
    const prev = this._frames[this._frames.length - 1];
    if (prev === undefined) return null;
    this._warnings.push({
      kind: "divergence",
      epoch,
      message: message("warn_nan", this._locale),
    });
    this._seenMilestones.add("divergence_warning");
    return {
      ...prev,
      seq: this._ctx.seq,
      grade: "F",
      narrative: narrateDiverged({
        epoch, metric, lastValue: prev.primaryMetricValue,
        lastEpoch: prev.epoch, runId: this._runId, locale: this._locale,
      }),
    };
  }

  private _checkMilestones(frame: StoryFrameMsg): void {
    // First improvement
    if (this._frames.length === 1 && !this._seenMilestones.has("first_metric")) {
      this._seenMilestones.add("first_metric");
      this._milestones.push({
        kind: "first_metric",
        epoch: frame.epoch,
        message: message("ms_first_metric", this._locale, {
          metric: displayMetric(this._primaryMetric, this._locale),
          value: frame.primaryMetricValue.toFixed(4),
        }),
      });
    }

    // Grade transitions
    const prevFrame = this._frames.length > 1
      ? this._frames[this._frames.length - 2]
      : null;
    if (prevFrame && prevFrame.grade !== frame.grade) {
      const key = `grade_${frame.grade}`;
      if (!this._seenMilestones.has(key)) {
        this._seenMilestones.add(key);
        // Every change used to read "Grade improved to …" — including a fall
        // to F.
        const rose = gradeRank(frame.grade) > gradeRank(prevFrame.grade);
        this._milestones.push({
          kind: "grade_transition",
          epoch: frame.epoch,
          message: message(rose ? "ms_grade_up" : "ms_grade_down", this._locale, {
            grade: frame.grade,
          }),
        });
      }
    }

    // Phase transitions
    if (prevFrame && prevFrame.phase !== frame.phase) {
      const key = `phase_${frame.phase}`;
      if (!this._seenMilestones.has(key)) {
        this._seenMilestones.add(key);
        this._milestones.push({
          kind: "phase_transition",
          epoch: frame.epoch,
          message: message("ms_phase", this._locale, {
            phase: message(`phase_${frame.phase}`, this._locale),
          }),
        });
      }
    }
  }

  /**
   * Mirrors story_engine/warnings.py. The only check here used to be "no value
   * went UP in the last five steps" — so a steadily FALLING loss, i.e. a
   * healthy run, was reported as a plateau.
   */
  private _checkWarnings(): void {
    const epoch = this._frames.length ? this._frames[this._frames.length - 1].epoch : null;
    const warn = (seen: string, kind: string, message: string): void => {
      if (this._seenMilestones.has(seen)) return;
      this._seenMilestones.add(seen);
      this._warnings.push({ kind, epoch, message });
    };

    // Plateau: the primary metric's span over the window is under 1% of where
    // the window began. Direction-free, which is what makes it correct.
    if (this._frames.length >= PLATEAU_WINDOW) {
      const w = this._frames.slice(-PLATEAU_WINDOW).map((f) => f.primaryMetricValue);
      const span = Math.max(...w) - Math.min(...w);
      if (span / (Math.abs(w[0]) + 1e-9) < PLATEAU_DELTA) {
        warn("plateau_warning", "plateau", message("warn_plateau", this._locale));
      }
    }

    // Overfitting: validation loss rising while training loss falls.
    const t = this._trainLosses;
    const v = this._valLosses;
    if (t.length >= OVERFIT_WINDOW && v.length >= OVERFIT_WINDOW) {
      const tw = t.slice(-OVERFIT_WINDOW);
      const vw = v.slice(-OVERFIT_WINDOW);
      const valRising = vw.every((x, i) => i === 0 || x > vw[i - 1]);
      const trainFalling = tw.every((x, i) => i === 0 || x < tw[i - 1]);
      if (valRising && trainFalling) {
        warn("overfit_warning", "overfit", message("warn_overfit", this._locale));
      }
    }

    // Divergence: a single 10x jump, or a climb to 10x the best loss seen. The
    // gradual case is the common one — 3.59 -> 2881 over eight epochs never
    // takes a single 10x step.
    if (t.length >= 2) {
      const last = t[t.length - 1];
      const prev = t[t.length - 2];
      if (last > prev * DIVERGE_GROWTH) {
        warn("divergence_warning", "divergence", message("warn_spike", this._locale));
      } else if (
        this._bestTrainLoss !== null && this._bestTrainLoss > 0 &&
        last > this._bestTrainLoss * DIVERGE_GROWTH
      ) {
        warn("divergence_warning", "divergence", message("warn_climb", this._locale));
      }
    }
    // Fold in only the losses seen since the last check: rescanning the whole
    // series on every frame is quadratic over a long run.
    for (; this._trainSeen < t.length; this._trainSeen++) {
      const x = t[this._trainSeen];
      if (Number.isFinite(x) && (this._bestTrainLoss === null || x < this._bestTrainLoss)) {
        this._bestTrainLoss = x;
      }
    }
  }
}

const GRADE_ORDER: Grade[] = ["F", "D", "C-", "C", "C+", "B-", "B", "B+", "A-", "A", "A+"];

/** Higher is better; "I" (incomplete) ranks below everything. */
function gradeRank(g: Grade): number {
  return GRADE_ORDER.indexOf(g);
}

function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
}

/** Exposed for tests. */
export const _internals = { canonicalise, detectTask, primaryMetricFrom };
