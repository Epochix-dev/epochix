/**
 * Open the current run in a real browser.
 *
 * The webview is convenient but constrained: it blocks downloads outright, and
 * exports have to be bounced out through the extension host to land anywhere.
 * A real browser has none of that, so this is both a nicety and the reliable
 * escape hatch when the panel cannot do what you need.
 */
import * as vscode from "vscode";

import type { ServerManager } from "../sidecar/ServerManager";
import { DashboardPanel } from "../webview/DashboardPanel";
import { openExternalUrl } from "../util/uri";

export function registerOpenInBrowser(
  context: vscode.ExtensionContext,
  getSidecar: () => ServerManager | null,
): void {
  context.subscriptions.push(
    vscode.commands.registerCommand("epochix.openInBrowser", async () => {
      const sidecar = getSidecar();
      if (!sidecar) {
        const pick = await vscode.window.showInformationMessage(
          "Epochix: opening in a browser needs the Python engine — the built-in " +
            "engine renders the story inside VS Code but does not serve it over HTTP.",
          "Install instructions",
        );
        if (pick) {
          void openExternalUrl(
            "https://github.com/epochix-dev/epochix#install",
          );
        }
        return;
      }

      // Deep-link to the run on screen when there is one; otherwise the run
      // list, which is a more useful landing place than an empty dashboard.
      const runId = DashboardPanel.current?.runId;
      const path = runId ? `/v/${encodeURIComponent(runId)}` : "/";
      void openExternalUrl(`http://127.0.0.1:${sidecar.port}${path}`);
    }),
  );
}
