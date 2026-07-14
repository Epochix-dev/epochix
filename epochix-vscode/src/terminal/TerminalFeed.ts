/**
 * TerminalFeed
 *
 * Decides which terminal output reaches the dashboard. Pure logic — no vscode
 * imports — so the terminal→dashboard journey can be driven deterministically
 * in tests instead of only through a real shell-integration session.
 *
 * Two rules, both of which the inline version in TerminalWatcher got wrong:
 *
 *  1. Detection needs to SEE some output before it fires, so the lines that
 *     triggered it are already in the buffer. They must be flushed to the
 *     dashboard, or the run starts mid-story with its first epochs missing.
 *
 *  2. Detection LATCHES. It used to be re-tested per chunk against a rolling
 *     8 KB tail, so a long non-metric blob mid-run could push the last "Epoch
 *     N/M" out of the window, flip isTraining() back to false, and silently
 *     stop feeding the dashboard for the rest of the run.
 */
import { isTraining, stripAnsi } from "./TrainingDetector";

// How much output to hold while waiting for detection to fire.
const BUFFER_TAIL = 8192;

export class TerminalFeed {
  private _buffer = "";
  private _detected = false;

  /** True once this stream has been recognised as training output. */
  get detected(): boolean {
    return this._detected;
  }

  /**
   * Offer one raw chunk of terminal output.
   *
   * Returns the text the dashboard should consume — the whole buffered
   * backlog on the chunk that trips detection, every chunk thereafter, and
   * `null` while we are still undecided.
   */
  push(chunk: string): string | null {
    const text = stripAnsi(chunk);

    if (this._detected) {
      return text;
    }

    this._buffer += text;
    if (this._buffer.length > BUFFER_TAIL) {
      this._buffer = this._buffer.slice(-BUFFER_TAIL);
    }

    if (!isTraining(this._buffer)) {
      return null;
    }

    // Latch, and hand over everything we withheld while deciding.
    this._detected = true;
    const backlog = this._buffer;
    this._buffer = "";
    return backlog;
  }

  reset(): void {
    this._buffer = "";
    this._detected = false;
  }
}
