import * as vscode from "vscode";
import { DashboardPanel } from "../webview/DashboardPanel";

const FORMAT_LABELS: Record<string, string> = {
  html: "Standalone HTML",
  pdf: "PDF report",
  md: "Markdown summary",
};

export function registerExportRun(
  _ctx: vscode.ExtensionContext,
): vscode.Disposable {
  return vscode.commands.registerCommand("epochix.exportRun", async () => {
    if (!DashboardPanel.current) {
      void vscode.window.showWarningMessage(
        "Epochix: No active run to export. Open a log file first.",
      );
      return;
    }

    const pick = await vscode.window.showQuickPick(
      Object.entries(FORMAT_LABELS).map(([id, label]) => ({
        label,
        description: `.${id}`,
        id,
      })),
      { placeHolder: "Export format" },
    );
    if (!pick) return;

    // Post message to webview which posts back to trigger the export
    void (DashboardPanel.current as unknown as { _post: (m: object) => void })
      ._post?.({ type: "requestExport", format: pick.id });
  });
}
