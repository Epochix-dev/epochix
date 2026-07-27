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
import { registerCompareRuns } from "./commands/compareRuns";
import { registerTryDemo } from "./commands/tryDemo";
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

  // Terminal watcher — always standalone: the sidecar has no endpoint that
  // accepts streamed terminal output, only a parse-this-file-on-disk one.
  const watcher = new TerminalWatcher(ctx.extensionUri, cfg.locale);

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
    registerCompareRuns(_sidecar),
    registerTryDemo(ctx, _sidecar),
  );

  // Show the install-sidecar hint at most ONCE (until the user acts), never
  // on every launch. It's suppressed after any interaction — and it never
  // shows again once the sidecar is detected, so users who fix their PATH or
  // set `epochix.sidecarPath` stop seeing it automatically.
  const NAG_KEY = "epochix.installHintDismissed";
  if (
    !_sidecar &&
    cfg.useSidecar !== "never" &&
    // In an untrusted folder there is no sidecar BY DESIGN, so "install the
    // package" is wrong — it is usually already installed. Saying it here also
    // burned the one-shot flag, so the user never saw the real hint after
    // trusting the folder.
    vscode.workspace.isTrusted &&
    !ctx.globalState.get<boolean>(NAG_KEY)
  ) {
    const guide = "Install guide";
    const standalone = "Use standalone";
    void vscode.window
      .showInformationMessage(
        "Epochix: install the `epochix` Python package for full features " +
          "(run history, HTML/PDF export, LLM fallback). Already installed? " +
          "Set `epochix.sidecarPath` to your epochix executable.",
        guide,
        standalone,
      )
      .then(async (choice) => {
        if (choice === guide) {
          void vscode.env.openExternal(
            vscode.Uri.parse("https://epochix.dev/quickstart/"),
          );
        } else if (choice === standalone) {
          await vscode.workspace
            .getConfiguration("epochix")
            .update("useSidecar", "never", vscode.ConfigurationTarget.Global);
        }
        // Any response (button or dismiss) silences the hint for good.
        await ctx.globalState.update(NAG_KEY, true);
      });
  }
}

export function deactivate(): void {
  _sidecar?.dispose();
  _sidecar = null;
}
