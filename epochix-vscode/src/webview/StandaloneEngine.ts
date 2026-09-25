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
  gradeNote,
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
import type { StoryFrameMsg, MilestoneMsg, WarningMsg, RunSummaryMsg } from "./messages";
import { parseArchitecture, type ArchLayer } from "../story/architecture";
import {
  ON_SCALE,
  PREFERRED_KEYS,
  SNIFF_SAMPLE_LINES,
  SNIFF_THRESHOLD,
  TASK_SIGNALS,
} from "../story/engineTables.generated";
import { canonicalise, isRecognised } from "../story/canonical";
import { FastAIParser } from "../parsers/fastai";
import { AccelerateParser } from "../parsers/accelerate";

// Metric names are canonicalised by story/canonical.ts — Python's
// canonicalize_key over tables generated from it.

// ── Task detection ────────────────────────────────────────────────────────────

// Nothing distinguishes a gaze model from any other regression except its
// names. Mirrors refine_gaze: classifying every MAE run as gaze graded a
// house-price MAE against bands built for angles in degrees.
const GAZE_HINT = /gaze|angular|pitch|yaw|eye_|_eye\b|fixation/i;

function detectTask(keys: ReadonlySet<string>, rawKeys: ReadonlySet<string>): TaskType {
  // First match wins, a run matching nothing is CUSTOM — as in Python.
  for (const [task, signals] of TASK_SIGNALS) {
    if ([...signals].some((s) => keys.has(s))) {
      if (task === "regression" && [...rawKeys].some((k) => GAZE_HINT.test(k))) {
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

/**
 * The key this run is narrated by — Python's _effective_primary_key: the
 * task's first preferred key that has been logged; for a CUSTOM run with none
 * of them, the first metric we do not recognise, under its own name; else the
 * task's default. `seen` is in the order keys were first logged.
 */
function primaryMetricFrom(task: TaskType, seen: ReadonlyArray<string>): string {
  const logged = new Set(seen);
  for (const key of PREFERRED_KEYS[task]) if (logged.has(key)) return key;
  if (task === "custom") {
    const unknown = seen.find((k) => !isRecognised(k));
    if (unknown !== undefined) return unknown;
  }
  return PREFERRED_KEYS[task][0] ?? "val_loss";
}

// Python's _clean_line: ANSI escapes and colour codes whose ESC byte was lost
// go, and a carriage-return redraw collapses to its final state.
// eslint-disable-next-line no-control-regex -- matching ESC is the point
const ANSI = /\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])/g;
const ORPHAN_SGR = /\[(?:\d{1,3}(?:;\d{1,3}){0,8})?m/g;
const MAX_LINE_LEN = 65536;

function cleanLine(text: string): string {
  let t = text.length > MAX_LINE_LEN ? text.slice(0, MAX_LINE_LEN) : text;
  t = t.replace(ANSI, "").replace(ORPHAN_SGR, "");
  if (t.endsWith("\r")) t = t.slice(0, -1);
  const cr = t.lastIndexOf("\r");
  return cr >= 0 ? t.slice(cr + 1) : t;
}

/** Every built-in parser, best first — fresh instances. */
function makeParsers(): Parser[] {
  return [
    new PytorchLightningParser(),
    new KerasParser(),
    new HuggingFaceParser(),
    new YoloParser(),
    new BoostingParser(),
    new FastAIParser(),
    new AccelerateParser(),
    new UniversalParser(),
  ].sort((a, b) => b.priority - a.priority);
}

// ── Engine ────────────────────────────────────────────────────────────────────

// As the Python pipeline: sample SNIFF_SAMPLE_LINES lines (or everything, at
// flush()/settle()) before choosing ONE parser. Deciding after six lines chose
// on a preamble — a Lightning banner, a YOLO model summary — and the old
// "best parser plus universal on every line" then read that banner's
// "using: 0" and every tqdm "[00:12" as metrics.
//
// Events before the task can first be classified; banked and replayed so no
// epoch is lost (Python: `_events_count >= 3`).
const WARMUP_EVENTS = 3;

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
  // Read recognised metrics off a line the chosen parser could not: every
  // other parser, best first (Python's _fallback_parsers).
  private _fallbacks: Parser[] = [];
  // Canonical keys in the order first logged, their raw names, and how many
  // readings of each — Python's _metric_history, _seen_raw_keys.
  private _seenKeys: string[] = [];
  private _rawKeys = new Set<string>();
  private _keyCounts = new Map<string, number>();
  private _eventsCount = 0;
  private _taskLocked = false;
  private _primaryKeyUsed: string | null = null;
  private _pending: string[] = [];
  private _warmup: WarmupLine[] = [];
  private _taskDetected = false;
  private _ctx: ParserContext = makeContext();

  private _runId = generateId();
  private _task: TaskType = "custom";
  private _primaryMetric = "val_loss";
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

  // The language the story is told in (`epochix.locale`). The engine used to
  // have English templates only, whatever the setting said.
  private readonly _locale: Locale;

  constructor(taskHint?: TaskType, locale?: string) {
    this._locale = resolveLocale(locale);
    this._parsers = makeParsers();

    // A task the user pinned (`epochix.taskHint`) is locked in, so detection
    // cannot overwrite it — it once did, and the setting did nothing.
    if (taskHint) {
      this._task = taskHint;
      this._taskLocked = true;
      this._primaryMetric = primaryMetricFrom(taskHint, []);
    }
  }

  /** Feed a chunk of text (may contain multiple lines). Returns new frames. */
  feed(text: string): StoryFrameMsg[] {
    this._buffer += text;
    const newFrames: StoryFrameMsg[] = [];

    // Process complete lines
    const parts = this._buffer.split(/\r?\n/);
    this._buffer = parts.pop() ?? "";
    const lines = parts.map(cleanLine);

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
      const last = cleanLine(this._buffer);
      this._buffer = "";
      if (this._activeParsers === null) this._pending.push(last);
      else newFrames.push(...this._processLine(last));
    }

    newFrames.push(...this.settle());

    // Metrics that only exist once the stream ends: a cross-validation's mean.
    const parser = this._activeParsers?.[0];
    const tail = parser?.flush ? parser.flush(this._ctx) : [];
    if (tail.length > 0) newFrames.push(...this._handleMetrics(tail));

    newFrames.push(...this._drainWarmup(true));
    return newFrames;
  }

  /**
   * Choose the parser now, on whatever has been sampled — Python's idle
   * flush. A live run shorter than the sniff window would otherwise draw
   * nothing until it ended; callers invoke this when output goes quiet.
   */
  settle(): StoryFrameMsg[] {
    if (this._activeParsers !== null || this._pending.length === 0) return [];
    this._activeParsers = this._selectParsers(this._pending);
    const backlog = this._pending;
    this._pending = [];
    const out: StoryFrameMsg[] = [];
    for (const held of backlog) out.push(...this._processLine(held));
    return out;
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

  /** Choose once the sniff window is full, as the Python pipeline does. */
  private _trySelectParsers(): boolean {
    if (this._pending.length < SNIFF_SAMPLE_LINES) return false;
    this._activeParsers = this._selectParsers(this._pending);
    return true;
  }

  /** Parse one line and turn it into a frame (or bank it during warmup). */
  private _processLine(line: string): StoryFrameMsg[] {
    this._ctx.seq++;
    let metrics = this._activeParsers![0].parseLine(line, this._ctx);
    if (metrics.length === 0 && this._fallbacks.length > 0) {
      metrics = this._fallbackMetrics(line);
    }

    // `loss: nan` never reaches the parsers — none of them reads a non-number.
    // Checked on the raw line, requiring `:` or `=` so prose cannot trip it.
    const nonFinite = NON_FINITE_ASSIGNMENT.exec(line);
    const frames = this._handleMetrics(metrics);
    if (nonFinite !== null && !this._diverged) {
      if (!this._taskDetected) frames.push(...this._drainWarmup(true));
      const frame = this._divergenceFrame(canonicalise(nonFinite[1]), this._ctx.currentEpoch);
      if (frame !== null) frames.push(this._emit(frame));
    }
    return frames;
  }

  /**
   * Recognised metrics the chosen parser could not read on this line —
   * Python's _fallback_metrics. Every other parser gets a look, best first,
   * each on a scratch context so prose cannot move the step axis: a
   * Lightning progress line inside a Keras log is read by the Lightning
   * parser (the universal one skips progress bars by design). A line that
   * carried real metrics also carried their epoch.
   */
  private _fallbackMetrics(line: string): RawMetric[] {
    for (const fallback of this._fallbacks) {
      const scratch: ParserContext = {
        ...this._ctx,
        axis: null,
        heldUnrecognised: new Map(),
        emittedKeys: new Set(),
        cvFolds: new Map(),
        cvCandidates: new Map(),
      };
      const metrics = fallback.parseLine(line, scratch).filter((m) => isRecognised(m.key));
      if (metrics.length > 0) {
        this._ctx.currentEpoch = scratch.currentEpoch;
        this._ctx.totalEpochs = scratch.totalEpochs;
        return metrics;
      }
    }
    return [];
  }

  /** One line's metrics: record them, then warm up or build a frame. */
  private _handleMetrics(metrics: RawMetric[]): StoryFrameMsg[] {
    this._allMetrics.push(...metrics);
    for (const m of metrics) {
      const key = canonicalise(m.key);
      if (!this._keyCounts.has(key)) this._seenKeys.push(key);
      this._keyCounts.set(key, (this._keyCounts.get(key) ?? 0) + 1);
      this._rawKeys.add(m.key);
      if (key === "train_loss") this._trainLosses.push(m.value);
      else if (key === "val_loss") this._valLosses.push(m.value);
    }
    this._eventsCount += metrics.length;
    this._classify();

    if (!this._taskDetected) {
      if (metrics.length > 0) {
        // Snapshot the epoch: these frames are built later, by which time the
        // parser context has moved on.
        this._warmup.push({
          metrics,
          epoch: this._ctx.currentEpoch,
          totalEpochs: this._ctx.totalEpochs,
        });
      }
      return this._eventsCount >= WARMUP_EVENTS ? this._drainWarmup(false) : [];
    }

    if (metrics.length === 0) return [];
    this._primaryMetric = primaryMetricFrom(this._task, this._seenKeys);
    const frame = this._buildFrame(metrics, this._ctx.currentEpoch, this._ctx.totalEpochs);
    return frame ? [this._emit(frame)] : [];
  }

  /**
   * Classify while the answer is still CUSTOM, locking only on a definite
   * task — Python's process_all. Locking after the first few metrics
   * classified a Hugging Face log on `loss` and `learning_rate` alone.
   */
  private _classify(force = false): void {
    if (this._taskLocked || (!force && this._eventsCount < WARMUP_EVENTS)) return;
    const detected = detectTask(new Set(this._seenKeys), this._rawKeys);
    if (detected !== "custom") {
      this._task = detected;
      this._taskLocked = true;
    }
  }

  /**
   * Detect the task from what we've seen, then replay every banked warmup line
   * so the epochs that arrived *before* detection still reach the dashboard.
   */
  private _drainWarmup(force: boolean): StoryFrameMsg[] {
    if (this._taskDetected) return [];
    if (this._allMetrics.length === 0) return [];
    if (!force && this._eventsCount < WARMUP_EVENTS) return [];

    // Flushed early (a log with fewer than three readings) the task is still
    // classified, as Python's flush_warmup does — otherwise a one-line result
    // stayed CUSTOM and found no metric to tell.
    if (force) this._classify(true);
    // Every banked line's keys count: Python replays its buffered events
    // with the whole buffer already in history.
    this._primaryMetric = primaryMetricFrom(this._task, this._seenKeys);
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

  /** detect_parser: the highest score in priority order, universal below the threshold. */
  private _selectParsers(sampleLines: readonly string[]): Parser[] {
    let best: Parser | null = null;
    let bestScore = -1;
    for (const p of this._parsers) {
      let score: number;
      try {
        score = p.sniff(sampleLines);
      } catch {
        score = 0;
      }
      if (score > bestScore) {
        bestScore = score;
        best = p;
      }
    }
    const universal = this._parsers.find((p) => p.name === "universal")!;
    const chosen = best === null || bestScore < SNIFF_THRESHOLD ? universal : best;
    // Fresh instances: some parsers keep state between lines (fastai's headers).
    this._fallbacks = makeParsers().filter((p) => p.name !== chosen.name);
    return [chosen];
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

    // The story's metric can change once the task is known (a run whose first
    // lines were only losses starts on the CUSTOM fallback). Restart the
    // baseline and best, so trajectory maths never mixes a loss with an
    // accuracy — as Python does.
    if (this._primaryKeyUsed !== null && this._primaryKeyUsed !== key) {
      this._baseline = null;
      this._best = null;
      this._bestEpoch = null;
      this._lastPrimary = value;
      this._primaryReadings = 0;
    }
    this._primaryKeyUsed = key;

    if (this._baseline === null) this._baseline = value;
    const delta = value - this._lastPrimary;
    this._lastPrimary = value;
    this._primaryReadings++;

    // Direction from the metric's own name first: the task default is right
    // for the task's headline metric and silently inverts every other one.
    const lowerBetter = metricLowerBetter(key) ?? taskLowerBetter(this._task);

    // Best so far, updated BEFORE the past-peak check, as in the Python engine.
    const newBest =
      this._best === null || (lowerBetter ? value < this._best : value > this._best);
    if (newBest || this._best === null) {
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
      primaryMetric: key,
      // The run's advancement, as in the Python engine — not the parser's
      // confidence in the line, which this carried and nothing displayed.
      confidence: progress,
      gradeNote: gradeNote(grade, this._primaryReadings, {
        hasEpoch: epoch !== null, newBest,
      }),
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
      // A divergence is certain, not provisional — as in the Python engine.
      gradeNote: null,
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
