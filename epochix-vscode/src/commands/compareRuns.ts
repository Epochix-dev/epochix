import * as vscode from "vscode";
import type { ServerManager } from "../sidecar/ServerManager";

/**
 * Epochix: Compare Two Runs.
 *
 * Comparison needs the run history, which only the Python sidecar keeps — the
 * standalone webview renders a single live stream and stores nothing. So this
 * opens the sidecar dashboard's run list, where the user selects runs and hits
 * "Compare" (the whole picker + overlay view already exists server-side).
 *
 * Previously this command was a placeholder that showed "coming in v0.2" — a
 * shipped no-op for a feature the Python side has had all along.
 */
export function registerCompareRuns(
  sidecar: ServerManager | null,
): vscode.Disposable {
  return vscode.commands.registerCommand("epochix.compareRuns", () => {
    if (!sidecar) {
      // Don't await — the command should return immediately, not stay "running"
      // until the dialog is dismissed. The button is handled asynchronously.
      void vscode.window
        .showInformationMessage(
          "Epochix: Comparing runs needs the epochix Python package (the sidecar " +
            "keeps run history — standalone mode stores nothing to compare).",
          "Install instructions",
        )
        .then((pick) => {
          if (pick === "Install instructions") {
            void vscode.env.openExternal(
              vscode.Uri.parse("https://github.com/epochix-dev/epochix#install"),
            );
          }
        });
      return;
    }

    // The dashboard root lists saved runs with select-to-compare checkboxes and
    // a "Compare" button that opens the overlay view.
    const url = `http://127.0.0.1:${sidecar.port}/`;
    void vscode.window.showInformationMessage(
      "Epochix: pick two or more runs and click Compare.",
    );
    void vscode.env.openExternal(vscode.Uri.parse(url));
  });
}
