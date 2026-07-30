/**
 * DashboardPanel — WebView panel manager for the Epochix dashboard.
 *
 * Lifecycle
 * ---------
 * - `createOrShow()` opens or focuses the panel.
 * - `openLog()` opens a specific log file and feeds lines to the standalone engine.
 * - `feedLines()` is called by TerminalWatcher with buffered terminal output.
 * - Panel disposes itself when closed; sets `DashboardPanel.current = undefined`.
 */
import * as vscode from "vscode";
import * as fs from "fs";
import * as readline from "readline";

import { buildWebviewHtml } from "./webview.html";
import type { ExtToWeb, StoryFrameMsg, WebToExt } from "./messages";
import type { ServerManager } from "../sidecar/ServerManager";
import * as path from "path";
import { persistLogFile } from "../sidecar/persistLog";
import { StatusBar } from "../statusBar";
import { StandaloneEngine } from "./StandaloneEngine";

export class DashboardPanel {
  static current: DashboardPanel | undefined;

  private readonly _panel: vscode.WebviewPanel;
  private _engine: StandaloneEngine | null;
  /** Set once the sidecar has persisted this run — the id the export routes need. */
  private _runId: string | undefined;
  private _architectureSent = false;
  private _metricsSent = 0;

  private _disposables: vscode.Disposable[] = [];
  private _sidecar: ServerManager | null;
  private readonly _locale: string;
  private readonly _theme: "light" | "dark";

  private constructor(
    panel: vscode.WebviewPanel,
    extensionUri: vscode.Uri,
    sidecar: ServerManager | null,
    locale: string,
    theme: "light" | "dark",
  ) {
    this._panel = panel;
    this._sidecar = sidecar;
    this._locale = locale;
    this._theme = theme;

    // Standalone engine is used when no sidecar is available
    this._engine = sidecar ? null : new StandaloneEngine();

    this._panel.webview.html = buildWebviewHtml({
      extensionUri,
      webview: this._panel.webview,
      sidecarUrl: sidecar ? `http://127.0.0.1:${sidecar.port}` : undefined,
      theme,
      locale,
    });

    this._panel.webview.onDidReceiveMessage(
      (msg: WebToExt) => this._handleWebMessage(msg),
      null,
      this._disposables,
    );

    this._panel.onDidDispose(() => this.dispose(), null, this._disposables);

    vscode.window.onDidChangeActiveColorTheme(
      (t) => {
        const newTheme = t.kind === vscode.ColorThemeKind.Light ? "light" : "dark";
        this._post({ type: "themeChange", theme: newTheme });
      },
      null,
      this._disposables,
    );
  }

  // ── Factory methods ──────────────────────────────────────────────────────────

  static createOrShow(
    extensionUri: vscode.Uri,
    sidecar: ServerManager | null,
    locale = "en",
  ): DashboardPanel {
    if (DashboardPanel.current) {
      DashboardPanel.current._panel.reveal(vscode.ViewColumn.Beside);
      return DashboardPanel.current;
    }

    const theme = resolveTheme();
    const panel = vscode.window.createWebviewPanel(
      "epochix.dashboard",
      "Epochix",
      { viewColumn: vscode.ViewColumn.Beside, preserveFocus: true },
      {
        enableScripts: true,
        retainContextWhenHidden: true,
        localResourceRoots: [vscode.Uri.joinPath(extensionUri, "webview-dist")],
      },
    );

    DashboardPanel.current = new DashboardPanel(
      panel, extensionUri, sidecar, locale, theme,
    );
    return DashboardPanel.current;
  }

  static openLog(
    extensionUri: vscode.Uri,
    fileUri: vscode.Uri,
    sidecar: ServerManager | null,
    locale = "en",
  ): void {
    const panel = DashboardPanel.createOrShow(extensionUri, sidecar, locale);

    if (sidecar) {
      // Parse locally, then persist through the sidecar's public API so the
      // run lands in saved history.
      persistLogFile(sidecar, fileUri.fsPath, path.basename(fileUri.fsPath))
        .then((runId) => {
          panel._runId = runId;
          panel._panel.webview.html = buildWebviewHtml({
            extensionUri,
            webview: panel._panel.webview,
            sidecarUrl: `http://127.0.0.1:${sidecar.port}/v/${runId}`,
            theme: resolveTheme(),
            locale,
          });
        })
        .catch((err: unknown) => {
          // The sidecar is unreachable (it died, never bound, or the port was
          // taken). We ship a complete standalone engine, so there is no
          // reason to fail here — degrade instead of leaving a dead panel
          // showing a raw ECONNREFUSED, which is what "Try a Demo Run" and
          // "Open Log File" both did when epochix was not on PATH.
          panel._degradeToStandalone(extensionUri, locale);
          panel._parseLogFile(fileUri.fsPath);
          void vscode.window.showWarningMessage(
            `Epochix: could not reach the Python engine (${describeSidecarError(err)}). ` +
              "Showing the story with the built-in engine instead — " +
              "everything works except saved run history.",
          );
        });
    } else {
      // Standalone: parse the file and push frames
      panel._parseLogFile(fileUri.fsPath);
    }
  }

  // ── Public methods ───────────────────────────────────────────────────────────

  /**
   * Feed buffered terminal text through the standalone engine.
   * Called by TerminalWatcher; no-op in sidecar mode.
   */
  feedLines(buffer: string): void {
    if (!this._engine) return;
    const frames = this._engine.feed(buffer);
    this._postArchitecture();
    this._postMetrics();
    for (const frame of frames) {
      this._post({ type: "frame", frame });
      StatusBar.update(frame);
    }
  }

  /**
   * The watched terminal command has ended — commit whatever the engine is
   * still holding (a short run can finish before the format sniff settles) and
   * publish the run summary.
   */
  endOfStream(): void {
    if (!this._engine) return;
    for (const frame of this._engine.flush()) {
      this._post({ type: "frame", frame });
      StatusBar.update(frame);
    }
    const summary = this._engine.finish();
    if (summary) {
      this._post({ type: "complete", run: summary });
    }
  }

  // ── Private ──────────────────────────────────────────────────────────────────

  private _post(msg: ExtToWeb): void {
    void this._panel.webview.postMessage(msg);
  }

  private _handleWebMessage(msg: WebToExt): void {
    switch (msg.type) {
      case "ready":
        this._sendInit();
        break;
      case "export":
        this._handleExport(msg.format, msg.runId ?? this._runId, msg.metric);
        break;
      case "openExternal":
        void vscode.env.openExternal(vscode.Uri.parse(msg.url));
        break;
      case "installSidecar":
        void vscode.env.openExternal(
          vscode.Uri.parse(
            "https://github.com/epochix-dev/epochix#install",
          ),
        );
        break;
      case "scrub":
        // Standalone engine: seek to seq
        this._engine?.scrubTo(msg.seq);
        break;
    }
  }

  private _handleExport(
    format: "html" | "pdf" | "md" | "json" | "gif",
    runId?: string,
    metric?: string,
  ): void {
    if (!this._sidecar) {
      void vscode.window.showInformationMessage(
        "Epochix: export needs the Python engine — the built-in engine renders " +
          "the story but cannot write files. Install it with: pip install 'epochix[gif]'",
      );
      return;
    }
    if (!runId) {
      // Previously this passed the literal string "current", on the assumption
      // that the server tracked an active run. It does not, so every export
      // 404'd. The id has to come from the run actually on screen.
      void vscode.window.showWarningMessage(
        "Epochix: this run was not saved to the Python engine, so it cannot be exported.",
      );
      return;
    }
    // The chosen series has to survive the trip out. Without it the extension
    // always exported the run's primary metric, so the picker offered choices
    // that changed nothing.
    const query = metric ? `?metric=${encodeURIComponent(metric)}` : "";
    void vscode.env.openExternal(
      vscode.Uri.parse(
        `http://127.0.0.1:${this._sidecar.port}/api/export/` +
          `${encodeURIComponent(runId)}/${format}${query}`,
      ),
    );
  }

  private _sendInit(): void {
    const hasSidecar = this._sidecar !== null;
    const snapshot: StoryFrameMsg[] = this._engine?.snapshot() ?? [];
    this._post({
      type: "init",
      theme: this._theme,
      locale: this._locale,
      snapshot,
      milestones: this._engine?.milestones() ?? [],
      warnings: this._engine?.warnings() ?? [],
      // Must ride along with init: a separate message posted before the
      // webview finishes its ready handshake is simply dropped, which is why
      // the Network State panel stayed empty even once detection worked.
      architecture: this._engine?.architecture() ?? [],
      metrics: this._engine?.metrics() ?? [],
      hasSidecar,
    });

    if (!hasSidecar) {
      this._post({ type: "installBanner", visible: true });
    }
  }

  /**
   * Drop the sidecar and switch this panel to the built-in engine.
   *
   * Rebuilds the webview without a sidecar URL so it renders locally rather
   * than pointing an iframe at a server that is not answering.
   */
  private _degradeToStandalone(extensionUri: vscode.Uri, locale: string): void {
    this._sidecar = null;
    this._engine = new StandaloneEngine();
    this._panel.webview.html = buildWebviewHtml({
      extensionUri,
      webview: this._panel.webview,
      sidecarUrl: undefined,
      theme: resolveTheme(),
      locale,
    });
  }

  /** Send the detected model layers once, when they first appear. */
  /** Send metric events parsed since the last call. */
  private _postMetrics(): void {
    const all = this._engine?.metrics() ?? [];
    if (all.length <= this._metricsSent) return;
    const fresh = all.slice(this._metricsSent);
    this._metricsSent = all.length;
    this._post({ type: "metrics", metrics: fresh });
  }

  private _postArchitecture(): void {
    const arch = this._engine?.architecture() ?? [];
    if (!arch.length || this._architectureSent) return;
    this._architectureSent = true;
    this._post({ type: "architecture", architecture: arch });
  }

  private _parseLogFile(filePath: string): void {
    if (!this._engine) return;

    const rl = readline.createInterface({
      input: fs.createReadStream(filePath, { encoding: "utf-8" }),
      crlfDelay: Infinity,
    });

    rl.on("line", (line) => {
      const frames = this._engine!.feed(line + "\n");
      for (const frame of frames) {
        this._post({ type: "frame", frame });
        StatusBar.update(frame);
      }
    });

    rl.on("close", () => {
      // Commit anything still held back by the format sniff — a short log can
      // end before the engine ever became confident, and those lines would
      // otherwise never be drawn.
      for (const frame of this._engine!.flush()) {
        this._post({ type: "frame", frame });
        StatusBar.update(frame);
      }
      const summary = this._engine!.finish();
      if (summary) {
        this._post({ type: "complete", run: summary });
      }
    });
  }

  dispose(): void {
    DashboardPanel.current = undefined;
    this._panel.dispose();
    for (const d of this._disposables) d.dispose();
    this._disposables = [];
  }
}

// ── helpers ───────────────────────────────────────────────────────────────────

/**
 * Turn a Node socket error into something a person can act on.
 *
 * A newcomer clicking "Try a Demo Run" should never be shown
 * "Error: connect ECONNREFUSED 127.0.0.1:7860".
 */
export function describeSidecarError(err: unknown): string {
  const msg = err instanceof Error ? err.message : String(err);
  if (msg.includes("ECONNREFUSED")) return "the local server is not responding";
  if (msg.includes("ETIMEDOUT")) return "the local server timed out";
  if (msg.includes("ECONNRESET")) return "the connection was reset";
  return msg;
}

function resolveTheme(): "light" | "dark" {
  return vscode.window.activeColorTheme.kind === vscode.ColorThemeKind.Light
    ? "light"
    : "dark";
}
