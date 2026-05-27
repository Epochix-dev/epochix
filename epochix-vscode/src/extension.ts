/**
 * Epochix — VS Code extension entry point.
 *
 * activate()   Called once when the extension becomes active.
 * deactivate() Called on shutdown (sidecar cleanup).
 */
import * as vscode from "vscode";

import { ServerManager } from "./sidecar/ServerManager";
import { TerminalWatcher } from "./terminal/TerminalWatcher";
import { StatusBar } from "./statusBar";
import { registerOpenDashboard } from "./commands/openDashboard";
import { registerWatchTerminal } from "./commands/watchTerminal";
import { registerOpenLogFile } from "./commands/openLogFile";
import { registerExportRun } from "./commands/exportRun";
import { getConfig } from "./config";

// Module-level sidecar reference — needed for deactivate()
let _sidecar: ServerManager | null = null;

export async function activate(ctx: vscode.ExtensionContext): Promise<void> {
  const cfg = getConfig();

  // Initialise status bar
  StatusBar.init(ctx);

  // Attempt to start sidecar server
  _sidecar = await ServerManager.maybeStart(
    vscode.workspace.getConfiguration("epochix"),
  );

  // Terminal watcher (standalone or sidecar)
  const watcher = new TerminalWatcher(_sidecar, ctx.extensionUri, cfg.locale);

  if (cfg.autoWatchTerminal) {
    watcher.attachToActiveAutomatically();
  }
  ctx.subscriptions.push(watcher);

  // Register commands
  ctx.subscriptions.push(
    registerOpenDashboard(ctx, _sidecar),
    registerWatchTerminal(watcher),
    registerOpenLogFile(ctx, _sidecar),
    registerExportRun(ctx),
    // compareRuns is a placeholder for future implementation
    vscode.commands.registerCommand("epochix.compareRuns", () => {
      void vscode.window.showInformationMessage(
        "Epochix: Run comparison coming in v0.2.",
      );
    }),
  );

  // Show install-sidecar notification to new users who don't have it
  if (!_sidecar && cfg.useSidecar !== "never") {
    const action = "Install epochix";
    void vscode.window
      .showInformationMessage(
        "Epochix: Install `pip install epochix` for full features " +
          "(history, HTML export, LLM fallback).",
        action,
        "Dismiss",
      )
      .then((choice) => {
        if (choice === action) {
          void vscode.env.openExternal(
            vscode.Uri.parse(
              "https://github.com/epochix/epochix#installation",
            ),
          );
        }
      });
  }
}

export function deactivate(): void {
  _sidecar?.dispose();
  _sidecar = null;
}
