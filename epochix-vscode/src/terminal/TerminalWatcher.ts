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
import { TerminalFeed } from "./TerminalFeed";

export class TerminalWatcher implements vscode.Disposable {
  private readonly _feed = new TerminalFeed();
  private _autoAttached = false;
  private readonly _subscriptions: vscode.Disposable[] = [];
  private _activeTerminal: vscode.Terminal | undefined;

  constructor(
    private readonly _extensionUri: vscode.Uri,
    private readonly _locale: string,
  ) {}

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
    void vscode.window.showInformationMessage(
      `Epochix: Watching terminal "${terminal.name}". ` +
        "Start your training command now.",
    );
  }

  // ── Private ──────────────────────────────────────────────────────────────────

  private async _consumeExecution(
    terminal: vscode.Terminal,
    execution: vscode.TerminalShellExecution,
  ): Promise<void> {
    const stream = execution.read();
    for await (const chunk of stream) {
      // TerminalFeed withholds output until it recognises training, then hands
      // back everything it buffered — so the epochs that TRIGGERED detection
      // still reach the dashboard instead of being dropped.
      const feedable = this._feed.push(chunk);
      if (feedable === null) continue;

      this._activeTerminal = terminal;
      this._openDashboardIfNeeded();
      this._feedDashboard(feedable);
    }

    // The command finished. Let the dashboard commit anything still held back
    // by the format sniff and post the run summary.
    if (this._feed.detected) {
      this._endOfStream();
    }
  }

  private _endOfStream(): void {
    // Deliberate: a lazy require breaks the DashboardPanel <-> TerminalWatcher
    // import cycle, which a top-level import would reintroduce.
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { DashboardPanel } = require("../webview/DashboardPanel") as {
      DashboardPanel: typeof import("../webview/DashboardPanel").DashboardPanel;
    };
    DashboardPanel.current?.endOfStream();
  }

  private _openDashboardIfNeeded(): void {
    // Lazy require to avoid circular dependency at module load time
    // Deliberate: a lazy require breaks the DashboardPanel <-> TerminalWatcher
    // import cycle, which a top-level import would reintroduce.
    // eslint-disable-next-line @typescript-eslint/no-var-requires
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
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { DashboardPanel } = require("../webview/DashboardPanel") as {
      DashboardPanel: typeof import("../webview/DashboardPanel").DashboardPanel;
    };
    DashboardPanel.current?.feedLines(chunk);
  }

  dispose(): void {
    for (const d of this._subscriptions) d.dispose();
    this._subscriptions.length = 0;
  }
}
