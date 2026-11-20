/**
 * One command's output in a watched terminal, and what Epochix made of it.
 *
 * TerminalFeed withholds a command's output until it recognises training, and
 * the dashboard opens only then. A command whose output is never recognised
 * produced nothing at all: no panel, no message. Both issues ever opened by
 * people outside the project were sent from an empty dashboard, and what
 * they ran is not known. This keeps the command's output (bounded) so that,
 * when it ends or goes quiet, the dashboard's own engine can be asked what it
 * would have told — and the person told when the answer is "nothing", or
 * "something, but the dashboard never opened".
 *
 * No second detector decides it. The verdict is the engine's: a fresh
 * StandaloneEngine, built as the panel builds its own (webview/panelEngine.ts),
 * reads the whole output and is flushed as the panel is when a command ends.
 * The one thing measured here that the engine does not is where a name the
 * normaliser recognises (canonical.ts, generated from Python) stands beside
 * numbers no reader took — a Stable-Baselines3 table, `| loss | 7.28 |` — so
 * that output in a layout nothing reads can be told apart from `ls`.
 *
 * Pure: no vscode import, so every recording can be driven through it in a test.
 */
import { isRecognised } from "../story/canonical";
import type { StandaloneEngine } from "../webview/StandaloneEngine";
import { TerminalFeed } from "./TerminalFeed";
import { stripAnsi } from "./TrainingDetector";

/**
 * Different values a recognised name must stand beside, on separate lines,
 * before output in a layout no reader takes counts as a training run. Of the
 * ordinary commands recorded in tests/fixtures/terminal (a listing, `git
 * log`, `pip install`, `pytest`, `npm install`, two web servers), the most any
 * of them shows is one — pytest printing `val_loss = 0.42` from a failing
 * test. A Stable-Baselines3 run shows `loss` beside 24.
 */
export const LABELLED_MIN_VALUES = 3;

/** Output kept for the verdict and for replaying into a dashboard. Beyond it
 *  the verdict reads the start of the output and says so, and the run is not
 *  offered to the dashboard, since only part of it would arrive. */
export const CAPTURE_LIMIT_CHARS = 4 * 1024 * 1024;

/** Longest line the scan below looks at, as the engine's own line cap. */
const MAX_LINE = 65536;

// A name, then only separators (spaces, a table's bars, `:`, `=`, `,`), then a
// number that does not run on into a word. Bounded throughout: an unbounded
// quantifier before a delimiter is O(n^2) on a long line (AGENTS.md).
const LABELLED = /(?<![\w./@-])([A-Za-z][\w@./-]{0,63})[ \t|:=,]{1,32}([-+]?\d{1,15}(?:\.\d{1,15})?(?:[eE][-+]?\d{1,3})?)(?![\w.])/g;

/** What Epochix made of a command it did not tell, or null to say nothing. */
export type Verdict =
  | {
      /** The dashboard's engine tells this run; the dashboard never opened. */
      kind: "unopened";
      lines: number;
      /** Lines the verdict was read from, when that is not all of them. */
      sampled: number | null;
      metric: string;
      /** Readings of that metric. */
      count: number;
      /** Whether the whole output is held, so it can be opened in the dashboard. */
      complete: boolean;
    }
  | {
      /** Output that looked like a training run and tells no story. */
      kind: "unread";
      lines: number;
      sampled: number | null;
      /** Whether the dashboard opened for it (and now has nothing to show). */
      opened: boolean;
      /** What the engine read, by canonical name, with how many readings. */
      readings: ReadonlyArray<readonly [string, number]>;
      /** Recognised names beside numbers no reader took, with how many
       *  different values stood beside each. */
      labelled: ReadonlyArray<readonly [string, number]>;
    };

/** Recognised names beside numbers, with the different values seen beside each
 *  on separate lines. A name with a path keeps its last part (`train/loss`). */
export function labelledNumbers(lines: readonly string[]): Map<string, number> {
  const values = new Map<string, Set<string>>();
  for (const raw of lines) {
    const line = raw.length > MAX_LINE ? raw.slice(0, MAX_LINE) : raw;
    const onLine = new Set<string>();
    for (const m of line.matchAll(LABELLED)) {
      const name = m[1].slice(m[1].lastIndexOf("/") + 1);
      if (onLine.has(name) || !isRecognised(name)) continue;
      onLine.add(name);
      const seen = values.get(name) ?? new Set<string>();
      seen.add(String(parseFloat(m[2])));
      values.set(name, seen);
    }
  }
  return new Map([...values].map(([name, seen]) => [name, seen.size]));
}

export class CommandReading {
  private readonly _feed = new TerminalFeed();
  private _chunks: string[] = [];
  private _chars = 0;
  private _truncated = false;
  private _newlines = 0;
  private _tail = "";
  private _ended = false;

  /**
   * Offer one raw chunk of the command's output. Returns what the dashboard
   * should consume, as TerminalFeed.push does.
   */
  push(chunk: string): string | null {
    const text = stripAnsi(chunk);
    for (let i = text.indexOf("\n"); i !== -1; i = text.indexOf("\n", i + 1)) this._newlines++;
    const cut = text.lastIndexOf("\n");
    this._tail = cut === -1 ? this._tail + text : text.slice(cut + 1);
    if (this._tail.length > MAX_LINE) this._tail = this._tail.slice(-MAX_LINE);
    if (!this._truncated) {
      if (this._chars + text.length > CAPTURE_LIMIT_CHARS) {
        this._truncated = true;
      } else {
        this._chunks.push(text);
        this._chars += text.length;
      }
    }
    return this._feed.push(chunk);
  }

  /** The command has finished. */
  end(): void {
    this._ended = true;
  }

  get ended(): boolean {
    return this._ended;
  }

  /** Whether the dashboard is reading this command. */
  get opened(): boolean {
    return this._feed.detected;
  }

  /** Lines the command printed, a last unterminated one included. */
  get lines(): number {
    return this._newlines + (this._tail.trim() === "" ? 0 : 1);
  }

  /** Whether every line of the output is held. */
  get complete(): boolean {
    return !this._truncated;
  }

  /**
   * Hand the dashboard this command from here on: what is held now, which
   * the caller feeds it, and every later chunk through push().
   */
  open(): string {
    this._feed.latch();
    return this._chunks.join("");
  }

  /**
   * What to say about this command, or null for nothing: told by the open
   * dashboard, not training, or not yet anything to go on.
   *
   * `engine` is a fresh engine built as the panel builds its own.
   */
  verdict(engine: StandaloneEngine): Verdict | null {
    const text = this._chunks.join("");
    if (text.trim() === "") return null;
    engine.feed(text);
    engine.flush();
    const frames = engine.snapshot();
    const lines = this.lines;
    const sampled = this._truncated ? text.split("\n").length - 1 : null;

    const readings = new Map<string, number[]>();
    for (const m of engine.metrics()) {
      const seen = readings.get(m.canonical_key) ?? [];
      seen.push(m.value);
      readings.set(m.canonical_key, seen);
    }

    // What the engine tells is a story only when its own test for one holds
    // (StandaloneEngine's wouldTell): a name it knows, a reading tied to an
    // epoch, or a cross-validation. `git log` is told as 209 frames of a
    // metric named `Date` and a web server's log as `INFO`; neither is one.
    const metric = engine.primaryMetricKey();
    const tellable =
      frames.length > 0 &&
      (isRecognised(metric) ||
        frames.some((f) => f.epoch !== null) ||
        engine.crossValidation() !== null);
    if (tellable) {
      if (this.opened) return null;
      return {
        kind: "unopened",
        lines,
        sampled,
        metric,
        count: readings.get(metric)?.length ?? 0,
        complete: !this._truncated,
      };
    }

    const read = [...readings].filter(([name]) => isRecognised(name));
    const labelled = [...labelledNumbers(text.split("\n"))].filter(
      ([name]) => !readings.has(name),
    );
    const looked =
      read.some(([, values]) => new Set(values).size >= LABELLED_MIN_VALUES) ||
      labelled.some(([, n]) => n >= LABELLED_MIN_VALUES);
    if (!looked) return null;
    return {
      kind: "unread",
      lines,
      sampled,
      opened: this.opened,
      readings: [...readings].map(([name, values]) => [name, values.length] as const),
      labelled: labelled.filter(([, n]) => n >= LABELLED_MIN_VALUES),
    };
  }
}
