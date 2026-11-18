/**
 * TerminalWatcher
 *
 * Uses VS Code's shell integration API (onDidStartTerminalShellExecution +
 * TerminalShellExecution.read()) to capture terminal output for training
 * detection and live dashboard feeding.
 *
 * Requires VS Code ≥ 1.93 with shell integration enabled in the terminal.
 * Falls back gracefully when shell integration is not available.
 */
import * as vscode from "vscode";
import { CommandReading } from "./CommandReading";
import { TerminalNotice } from "./notice";
import { noticeText } from "./noticeText";
import { openExternalUrl } from "../util/uri";
import { panelEngine } from "../webview/panelEngine";

/** How long a command must be silent before what it printed is judged. */
export const QUIET_MS = 5000;
/** How often a command that never goes quiet is judged while it runs. */
export const JUDGE_EVERY_MS = 30000;

export interface WatcherTimings {
  quietMs?: number;
  judgeEveryMs?: number;
}

export class TerminalWatcher implements vscode.Disposable {
  private _autoAttached = false;
  private readonly _subscriptions: vscode.Disposable[] = [];
  private _activeTerminal: vscode.Terminal | undefined;
  private readonly _notice: TerminalNotice;
  private readonly _quietMs: number;
  private readonly _judgeEveryMs: number;

  constructor(
    private readonly _extensionUri: vscode.Uri,
    private readonly _locale: string,
    timings: WatcherTimings = {},
  ) {
    this._quietMs = timings.quietMs ?? QUIET_MS;
    this._judgeEveryMs = timings.judgeEveryMs ?? JUDGE_EVERY_MS;
    this._notice = new TerminalNotice(_locale);
  }

  /** The notice saying a command was seen and not told, for tests. */
  get notice(): TerminalNotice {
    return this._notice;
  }

  /**
   * Attach to all terminals and auto-open dashboard when training is detected.
   */
  attachToActiveAutomatically(): void {
    if (this._autoAttached) return;
    this._autoAttached = true;

    // Modern shell integration API (VS Code ≥ 1.93)
    this._subscriptions.push(
      vscode.window.onDidStartTerminalShellExecution(
        (e: vscode.TerminalShellExecutionStartEvent) => {
          // Only track one terminal at a time
          if (
            this._activeTerminal !== undefined &&
            this._activeTerminal !== e.terminal
          ) {
            return;
          }
          void this._consumeExecution(e.terminal, e.execution);
        },
      ),
    );
  }

  /** Manually attach to the currently focused terminal's next command. */
  attachToActive(): void {
    const terminal = vscode.window.activeTerminal;
    if (!terminal) {
      void vscode.window.showWarningMessage(
        "Epochix: No active terminal found.",
      );
      return;
    }
    // Make sure we are actually listening for shell executions. The listener
    // was only ever registered by attachToActiveAutomatically(), which
    // extension.ts skips when `epochix.autoWatchTerminal` is false — so this
    // command used to announce "Watching terminal X" and then capture nothing.
    this.attachToActiveAutomatically();
    this._activeTerminal = terminal;

    // Everything here rides on shell integration: without it
    // onDidStartTerminalShellExecution never fires and we capture nothing.
    // Promising "watching" and then sitting silent is the same failure this
    // command already had once for a different reason (see above) — say so
    // instead. It activates a moment after a terminal opens, so an absent
    // `shellIntegration` is "not yet" rather than "never"; the wording has to
    // carry that or it becomes a false alarm on a freshly opened terminal.
    if (terminal.shellIntegration === undefined) {
      void vscode.window
        .showWarningMessage(
          `Epochix: shell integration is not active in "${terminal.name}" yet, ` +
            "so training output cannot be read. It usually activates a second " +
            "after the terminal opens — if it does not, your shell may not " +
            "support it, and you can pipe instead: python train.py | epochix",
          "How do I fix this?",
        )
        .then((choice) => {
          if (choice === "How do I fix this?") {
            void openExternalUrl(
              "https://code.visualstudio.com/docs/terminal/shell-integration",
            );
          }
        });
      return;
    }

    void vscode.window.showInformationMessage(
      `Epochix: Watching terminal "${terminal.name}". ` +
        "Start your training command now.",
    );
  }

  // ── Private ──────────────────────────────────────────────────────────────────

  private async _consumeExecution(
    terminal: vscode.Terminal,
    execution: Pick<vscode.TerminalShellExecution, "read">,
  ): Promise<void> {
    // One reading per command. A single feed for the whole session latched on
    // the first training run, and every command after it — an `ls`, a `git
    // status` — was fed to that run's dashboard.
    const reading = new CommandReading();
    let quiet: ReturnType<typeof setTimeout> | undefined;
    let judged = Date.now();

    const stream = execution.read();
    for await (const chunk of stream) {
      // TerminalFeed withholds output until it recognises training, then hands
      // back everything it buffered — so the epochs that TRIGGERED detection
      // still reach the dashboard instead of being dropped.
      const feedable = reading.push(chunk);
      if (feedable !== null) {
        this._activeTerminal = terminal;
        this._openDashboardIfNeeded();
        this._feedDashboard(feedable);
        // Recognised after all: whatever was said about it no longer stands.
        this._notice.withdraw(reading);
        continue;
      }

      // Not recognised (yet). Judge it when it goes quiet, and now and then
      // when it never does — a run in a layout nothing reads may print for
      // hours, and its end is too late to hear that nothing was understood.
      if (quiet !== undefined) clearTimeout(quiet);
      quiet = setTimeout(() => this._judge(reading), this._quietMs);
      if (Date.now() - judged >= this._judgeEveryMs) {
        judged = Date.now();
        this._judge(reading);
      }
    }
    if (quiet !== undefined) clearTimeout(quiet);
    reading.end();

    // The command finished. Let the dashboard commit anything still held back
    // by the format sniff and post the run summary.
    if (reading.opened) {
      this._endOfStream();
    }
    this._judge(reading);
  }

  /**
   * Say what was made of a command, if there is something to say. While it
   * runs, only a command the dashboard is not reading is judged: an open
   * dashboard may simply not have reached its first epoch.
   */
  private _judge(reading: CommandReading): void {
    if (!reading.ended && reading.opened) return;
    const verdict = reading.verdict(panelEngine(this._locale));
    if (verdict === null) {
      if (reading.ended) this._notice.withdraw(reading);
      return;
    }
    this._notice.show(reading, noticeText(verdict, this._locale), () => this._openReading(reading));
  }

  /** Open a command the dashboard can tell but never recognised. */
  private _openReading(reading: CommandReading): void {
    this._openDashboardIfNeeded();
    this._feedDashboard(reading.open());
    if (reading.ended) this._endOfStream();
  }

  private _endOfStream(): void {
    // Deliberate: a lazy require breaks the DashboardPanel <-> TerminalWatcher
    // import cycle, which a top-level import would reintroduce.
    // typescript-eslint v8 renamed this rule from no-var-requires.
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { DashboardPanel } = require("../webview/DashboardPanel") as {
      DashboardPanel: typeof import("../webview/DashboardPanel").DashboardPanel;
    };
    DashboardPanel.current?.endOfStream();
  }

  private _openDashboardIfNeeded(): void {
    // Lazy require to avoid circular dependency at module load time
    // Deliberate: a lazy require breaks the DashboardPanel <-> TerminalWatcher
    // import cycle, which a top-level import would reintroduce.
    // typescript-eslint v8 renamed this rule from no-var-requires.
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { DashboardPanel } = require("../webview/DashboardPanel") as {
      DashboardPanel: typeof import("../webview/DashboardPanel").DashboardPanel;
    };
    if (!DashboardPanel.current) {
      // Always standalone: terminal output reaches the dashboard ONLY through
      // DashboardPanel.feedLines -> StandaloneEngine, and feedLines is a no-op
      // when a sidecar owns the panel (the sidecar has no terminal-ingest
      // endpoint — it can only parse a file on disk). Passing the sidecar here
      // therefore made "Watch Active Terminal" silently show nothing for every
      // user who had the Python package installed.
      DashboardPanel.createOrShow(this._extensionUri, null, this._locale);
    }
  }

  private _feedDashboard(chunk: string): void {
    // Deliberate: a lazy require breaks the DashboardPanel <-> TerminalWatcher
    // import cycle, which a top-level import would reintroduce.
    // typescript-eslint v8 renamed this rule from no-var-requires.
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { DashboardPanel } = require("../webview/DashboardPanel") as {
      DashboardPanel: typeof import("../webview/DashboardPanel").DashboardPanel;
    };
    DashboardPanel.current?.feedLines(chunk);
  }

  dispose(): void {
    for (const d of this._subscriptions) d.dispose();
    this._subscriptions.length = 0;
    this._notice.dispose();
  }
}
