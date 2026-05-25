/**
 * DashboardPanel — WebView panel manager for the Model Story dashboard.
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
import { StatusBar } from "../statusBar";
import { StandaloneEngine } from "./StandaloneEngine";

export class DashboardPanel {
  static current: DashboardPanel | undefined;

  private readonly _panel: vscode.WebviewPanel;
  private readonly _engine: StandaloneEngine | null;
  private _disposables: vscode.Disposable[] = [];
  private readonly _sidecar: ServerManager | null;
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
      "modelStory.dashboard",
      "Model Learning Story",
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
      // Ask sidecar to parse + register the log file
      sidecar
        .parseLogFile(fileUri.fsPath)
        .then((runId) => {
          panel._panel.webview.html = buildWebviewHtml({
            extensionUri,
            webview: panel._panel.webview,
            sidecarUrl: `http://127.0.0.1:${sidecar.port}/v/${runId}`,
            theme: resolveTheme(),
            locale,
          });
        })
        .catch((err: unknown) => {
          void vscode.window.showErrorMessage(
            `Model Story: Failed to parse log — ${String(err)}`,
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
    for (const frame of frames) {
      this._post({ type: "frame", frame });
      StatusBar.update(frame);
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
        this._handleExport(msg.format);
        break;
      case "openExternal":
        void vscode.env.openExternal(vscode.Uri.parse(msg.url));
        break;
      case "installSidecar":
        void vscode.env.openExternal(
          vscode.Uri.parse(
            "https://github.com/model-story/model-story#installation",
          ),
        );
        break;
      case "scrub":
        // Standalone engine: seek to seq
        this._engine?.scrubTo(msg.seq);
        break;
    }
  }

  private _handleExport(format: "html" | "pdf" | "md"): void {
    if (this._sidecar) {
      // With sidecar: open the export URL in the browser
      const runId = "current"; // sidecar tracks the active run
      void vscode.env.openExternal(
        vscode.Uri.parse(
          `http://127.0.0.1:${this._sidecar.port}/api/export/${runId}/${format}`,
        ),
      );
    } else {
      void vscode.window.showInformationMessage(
        `Model Story: HTML/PDF export requires the Python sidecar. ` +
          `Install with: pip install model-story`,
      );
    }
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
      hasSidecar,
    });

    if (!hasSidecar) {
      this._post({ type: "installBanner", visible: true });
    }
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

function resolveTheme(): "light" | "dark" {
  return vscode.window.activeColorTheme.kind === vscode.ColorThemeKind.Light
    ? "light"
    : "dark";
}
