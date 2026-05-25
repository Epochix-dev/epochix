import * as vscode from "vscode";
import { DashboardPanel } from "../webview/DashboardPanel";
import type { ServerManager } from "../sidecar/ServerManager";
import { getConfig } from "../config";

export function registerOpenLogFile(
  ctx: vscode.ExtensionContext,
  sidecar: ServerManager | null,
): vscode.Disposable {
  return vscode.commands.registerCommand(
    "modelStory.openLogFile",
    async (uri?: vscode.Uri) => {
      const { locale } = getConfig();

      // If called from explorer context menu, uri is provided.
      // If called from command palette, ask the user.
      let fileUri = uri;
      if (!fileUri) {
        const chosen = await vscode.window.showOpenDialog({
          canSelectMany: false,
          canSelectFolders: false,
          filters: { "Log files": ["log", "txt", "out"] },
          openLabel: "Open with Model Story",
        });
        fileUri = chosen?.[0];
      }

      if (!fileUri) return;
      DashboardPanel.openLog(ctx.extensionUri, fileUri, sidecar, locale);
    },
  );
}
