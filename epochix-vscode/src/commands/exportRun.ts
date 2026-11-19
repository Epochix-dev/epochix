import * as vscode from "vscode";
import { DashboardPanel } from "../webview/DashboardPanel";

const FORMAT_LABELS: Record<"html" | "pdf" | "md", string> = {
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

    const formats = Object.keys(FORMAT_LABELS) as (keyof typeof FORMAT_LABELS)[];
    const pick = await vscode.window.showQuickPick(
      formats.map((id) => ({ label: FORMAT_LABELS[id], description: `.${id}`, id })),
      { placeHolder: "Export format" },
    );
    if (!pick) return;

    // The panel's own export: the Python engine's file, or the reason there
    // is none. This posted a `requestExport` message to the webview, which
    // nothing in the webview, the server or the panel ever handled, so the
    // command did nothing after the format was picked, every time.
    DashboardPanel.current.exportRun(pick.id);
  });
}
