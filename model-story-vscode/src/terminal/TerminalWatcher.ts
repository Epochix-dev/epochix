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
import { isTraining, stripAnsi } from "./TrainingDetector";
import type { ServerManager } from "../sidecar/ServerManager";

// How much terminal output to accumulate before trimming
const BUFFER_TAIL = 8192;

export class TerminalWatcher implements vscode.Disposable {
  private _buffer = "";
  private _autoAttached = false;
  private readonly _subscriptions: vscode.Disposable[] = [];
  private _activeTerminal: vscode.Terminal | undefined;

  constructor(
    private readonly _sidecar: ServerManager | null,
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
        "Model Story: No active terminal found.",
      );
      return;
    }
    this._activeTerminal = terminal;
    void vscode.window.showInformationMessage(
      `Model Story: Watching terminal "${terminal.name}". ` +
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
      const text = stripAnsi(chunk);
      this._buffer += text;
      if (this._buffer.length > BUFFER_TAIL) {
        this._buffer = this._buffer.slice(-BUFFER_TAIL);
      }

      if (isTraining(this._buffer)) {
        this._activeTerminal = terminal;
        this._openDashboardIfNeeded();
        this._feedDashboard(text);
      }
    }
  }

  private _openDashboardIfNeeded(): void {
    // Lazy require to avoid circular dependency at module load time
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { DashboardPanel } = require("../webview/DashboardPanel") as {
      DashboardPanel: typeof import("../webview/DashboardPanel").DashboardPanel;
    };
    if (!DashboardPanel.current) {
      DashboardPanel.createOrShow(this._extensionUri, this._sidecar, this._locale);
    }
  }

  private _feedDashboard(chunk: string): void {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
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
