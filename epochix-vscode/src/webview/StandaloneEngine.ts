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
import type { Phase } from "../story/phases";
import {
  computePhase,
  estimateProgress,
} from "../story/phases";
import type { Grade, TaskType } from "../story/grader";
import { computeGrade } from "../story/grader";
import { narrate } from "../story/narrator";
import type { StoryFrameMsg, MilestoneMsg, WarningMsg, RunSummaryMsg } from "./messages";

// ── Canonical key normalisation ───────────────────────────────────────────────

const CANONICAL_MAP: Record<string, string> = {
  val_acc: "val_accuracy", val_accy: "val_accuracy",
  accuracy: "val_accuracy", acc: "val_accuracy",
  train_acc: "train_accuracy",
  loss: "train_loss", train_loss: "train_loss",
  val_loss: "val_loss", validation_loss: "val_loss",
  map50: "mAP50", "mAP50-95": "mAP", map: "mAP",
  perplexity: "perplexity", ppl: "perplexity",
  eer: "EER", equal_error_rate: "EER",
  mae: "MAE", mean_absolute_error: "MAE",
};

function canonicalise(key: string): string {
  const lo = key.toLowerCase().replace(/-/g, "_");
  return CANONICAL_MAP[lo] ?? CANONICAL_MAP[key] ?? key;
}

// ── Task detection ────────────────────────────────────────────────────────────

function detectTask(metrics: readonly RawMetric[]): TaskType {
  const keys = new Set(metrics.map((m) => canonicalise(m.key).toLowerCase()));
  if (keys.has("map50") || keys.has("map")) return "detection";
  if (keys.has("perplexity") || keys.has("ppl")) return "nlp";
  if (keys.has("eer") || keys.has("equal_error_rate")) return "biometric";
  if (keys.has("mae") && !keys.has("val_accuracy")) return "gaze";
  return "classification";
}

function primaryMetricFor(task: TaskType): string {
  switch (task) {
    case "detection": return "mAP50";
    case "nlp": return "perplexity";
    case "biometric": return "EER";
    case "gaze": return "MAE";
    case "regression": return "MAE";
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
  private _allMetrics: RawMetric[] = [];
  private _frames: StoryFrameMsg[] = [];
  private _milestones: MilestoneMsg[] = [];
  private _warnings: WarningMsg[] = [];
  private _seenMilestones = new Set<string>();
  private _buffer = "";

  constructor(taskHint?: TaskType) {
    this._parsers = [
      new PytorchLightningParser(),
      new KerasParser(),
      new HuggingFaceParser(),
      new YoloParser(),
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

    this._task = detectTask(this._allMetrics);
    this._primaryMetric = primaryMetricFor(this._task);
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

    if (this._baseline === null) this._baseline = value;
    const delta = value - this._lastPrimary;
    this._lastPrimary = value;

    const progress = estimateProgress(epoch, totalEpochs);
    const phase: Phase = computePhase(progress, value, this._baseline, 1.0);
    const grade: Grade = computeGrade(this._task, value);

    const narrative = narrate({
      task: this._task,
      phase,
      epoch,
      primaryValue: value,
      delta,
      runId: this._runId,
    });

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

  private _checkMilestones(frame: StoryFrameMsg): void {
    // First improvement
    if (this._frames.length === 1 && !this._seenMilestones.has("first_metric")) {
      this._seenMilestones.add("first_metric");
      this._milestones.push({
        kind: "first_metric",
        epoch: frame.epoch,
        message: `First ${this._primaryMetric} recorded: ${frame.primaryMetricValue.toFixed(4)}`,
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
        this._milestones.push({
          kind: "grade_transition",
          epoch: frame.epoch,
          message: `Grade improved to ${frame.grade}`,
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
          message: `Entered ${frame.phase} phase`,
        });
      }
    }
  }

  private _checkWarnings(): void {
    if (this._frames.length < 5) return;

    const recent = this._frames.slice(-5).map((f) => f.primaryMetricValue);
    const improving = recent.some((v, i) => i > 0 && v > recent[i - 1]);

    if (!improving && !this._seenMilestones.has("plateau_warning")) {
      this._seenMilestones.add("plateau_warning");
      this._warnings.push({
        kind: "plateau",
        epoch: this._frames[this._frames.length - 1].epoch,
        message: "Training may be plateauing — no improvement over the last 5 steps.",
      });
    }
  }
}

function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
}
