/**
 * What an open run looks like graded again.
 *
 * The panel kept the thresholds it was opened with: a `.epochix.yaml` added or
 * edited while a run was on screen applied from the next run only. The panel
 * keeps the text it was fed (up to a cap) so that, when the file changes, the
 * run can be read again from the start with the new thresholds — the same
 * input through a fresh engine, not a re-labelling of the old frames.
 */
import type { GradeConfig } from "../story/gradeConfig";
import type { TaskType } from "../story/grader";
import type { RunSummaryMsg } from "./messages";
import { StandaloneEngine } from "./StandaloneEngine";

/** Text kept for a re-read. A longer run is not kept, and is not re-read. */
export const REPLAY_LIMIT_CHARS = 32 * 1024 * 1024;

/** The text a panel was fed, in order, while it fits under the limit. */
export class ReplayBuffer {
  private _chunks: string[] = [];
  private _chars = 0;
  private _overflowed = false;
  private _ended = false;

  constructor(private readonly _limit: number = REPLAY_LIMIT_CHARS) {}

  add(chunk: string): void {
    if (this._overflowed) return;
    this._chars += chunk.length;
    if (this._chars > this._limit) {
      // Keeping part of a run would re-read part of a run.
      this._overflowed = true;
      this._chunks = [];
      return;
    }
    this._chunks.push(chunk);
  }

  /** The run's input has ended (a file read through, a command finished). */
  end(): void {
    this._ended = true;
  }

  get ended(): boolean {
    return this._ended;
  }

  /** Whether the whole input is held, so a re-read gives the whole run. */
  get complete(): boolean {
    return !this._overflowed;
  }

  get empty(): boolean {
    return this._chunks.length === 0;
  }

  get chunks(): readonly string[] {
    return this._chunks;
  }
}

/**
 * The run in `buffer` read again by a fresh engine with `config`, and its
 * summary if the input had ended. Null when the buffer cannot give the whole
 * run.
 */
export function regrade(
  buffer: ReplayBuffer,
  config: GradeConfig | null,
  taskHint: TaskType | undefined,
  locale: string,
): { engine: StandaloneEngine; summary: RunSummaryMsg | null } | null {
  if (!buffer.complete) return null;
  const engine = new StandaloneEngine(taskHint, locale, config);
  for (const chunk of buffer.chunks) engine.feed(chunk);
  if (!buffer.ended) {
    engine.settle();
    return { engine, summary: null };
  }
  engine.flush();
  return { engine, summary: engine.finish() };
}
