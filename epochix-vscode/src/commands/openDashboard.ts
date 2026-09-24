import * as vscode from "vscode";
import { DashboardPanel } from "../webview/DashboardPanel";
import type { ServerManager } from "../sidecar/ServerManager";
import { getConfig } from "../config";

export function registerOpenDashboard(
  ctx: vscode.ExtensionContext,
  sidecar: ServerManager | null,
): vscode.Disposable {
  return vscode.commands.registerCommand("epochix.openDashboard", () => {
    const { locale } = getConfig();
    DashboardPanel.createOrShow(ctx.extensionUri, sidecar, locale);
  });
}
