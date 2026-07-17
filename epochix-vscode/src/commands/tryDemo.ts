import * as vscode from "vscode";
import { DashboardPanel } from "../webview/DashboardPanel";
import type { ServerManager } from "../sidecar/ServerManager";
import { getConfig } from "../config";

/**
 * Epochix: Try a Demo Run.
 *
 * The one-click, zero-setup path: opens the dashboard on a bundled training
 * log (a real Keras image-classifier run, model summary included, so the
 * architecture panel lights up too). No Python, no data, no training script —
 * a newcomer sees the product in one click.
 *
 * Works in both modes: with the sidecar the log is parsed and saved by the
 * Python engine; standalone it renders through the built-in engine.
 */
export function registerTryDemo(
  ctx: vscode.ExtensionContext,
  sidecar: ServerManager | null,
): vscode.Disposable {
  return vscode.commands.registerCommand("epochix.tryDemo", () => {
    const demo = vscode.Uri.joinPath(ctx.extensionUri, "media", "demo.log");
    const { locale } = getConfig();
    DashboardPanel.openLog(ctx.extensionUri, demo, sidecar, locale);
  });
}
