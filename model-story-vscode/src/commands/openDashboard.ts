import * as vscode from "vscode";
import { DashboardPanel } from "../webview/DashboardPanel";
import type { ServerManager } from "../sidecar/ServerManager";
import { getConfig, resolvedTheme } from "../config";

export function registerOpenDashboard(
  ctx: vscode.ExtensionContext,
  sidecar: ServerManager | null,
): vscode.Disposable {
  return vscode.commands.registerCommand("modelStory.openDashboard", () => {
    const { locale } = getConfig();
    void resolvedTheme(); // warm cache
    DashboardPanel.createOrShow(ctx.extensionUri, sidecar, locale);
  });
}
