/**
 * What happens when the Python sidecar is not reachable.
 *
 * A cold-start usability test on a fresh machine hit this on BOTH flagship
 * onboarding buttons — "Try a Demo Run" and "Open Log File" — and got a raw
 * "connect ECONNREFUSED 127.0.0.1:7860" with a dead, empty dashboard. The
 * extension ships a complete standalone engine, so that never had to happen.
 *
 * The existing demo test could not have caught it: it forces
 * `useSidecar: "never"`, which is the mode that already worked.
 */
import * as assert from "assert";
import * as path from "path";

import * as vscode from "vscode";

import { DashboardPanel, describeSidecarError } from "../../webview/DashboardPanel";
import type { ServerManager } from "../../sidecar/ServerManager";

const EXT_ID = "epochix.epochix";

/** A sidecar that is registered but answers nothing — a dead server. */
function deadSidecar(): ServerManager {
  return {
    port: 1,
    parseLogFile: () =>
      Promise.reject(new Error("connect ECONNREFUSED 127.0.0.1:1")),
    dispose: () => undefined,
  } as unknown as ServerManager;
}

suite("Sidecar unreachable — the dashboard must still tell the story", () => {
  test("openLog falls back to the standalone engine and renders frames", async () => {
    const ext = vscode.extensions.getExtension(EXT_ID);
    assert.ok(ext, `extension ${EXT_ID} not found`);
    await ext.activate();

    const demo = vscode.Uri.file(
      path.join(ext.extensionPath, "media", "demo.log"),
    );

    DashboardPanel.openLog(ext.extensionUri, demo, deadSidecar(), "en");
    await new Promise((r) => setTimeout(r, 3000)); // reject → degrade → parse

    const panel = DashboardPanel.current;
    assert.ok(panel, "no dashboard panel was created");

    // White-box on purpose: the point is that the panel switched engines
    // rather than sitting dead. TS `private` is compile-time only.
    const inner = panel as unknown as {
      _engine: { snapshot: () => unknown[] } | null;
      _sidecar: unknown;
    };
    assert.ok(
      inner._engine,
      "panel did not degrade to the standalone engine after the sidecar failed",
    );
    assert.strictEqual(
      inner._sidecar,
      null,
      "panel kept pointing at the dead sidecar",
    );
    assert.ok(
      inner._engine.snapshot().length > 0,
      "degraded panel produced no story frames from the demo log",
    );
  });

  test("a watched terminal still gets an engine when a sidecar is running", async () => {
    // TerminalWatcher used to hand its panel the sidecar, but terminal output
    // reaches the dashboard ONLY via feedLines -> StandaloneEngine, and
    // feedLines is a no-op when a sidecar owns the panel. So "Watch Active
    // Terminal" silently showed nothing for everyone who had the Python
    // package installed — the opposite failure to the demo button's.
    const ext = vscode.extensions.getExtension(EXT_ID);
    assert.ok(ext);
    await ext.activate();

    DashboardPanel.current?.dispose();
    const { TerminalWatcher } = await import("../../terminal/TerminalWatcher");
    const watcher = new TerminalWatcher(ext.extensionUri, "en");

    // Drive the private open path the shell-execution listener uses.
    (watcher as unknown as { _openDashboardIfNeeded: () => void })
      ._openDashboardIfNeeded();

    const panel = DashboardPanel.current;
    assert.ok(panel, "watching a terminal opened no dashboard");
    const inner = panel as unknown as { _engine: unknown };
    assert.ok(
      inner._engine,
      "the terminal dashboard has no engine — every chunk fed to it is dropped",
    );
    watcher.dispose();
  });

  test("socket errors are never shown to the user verbatim", () => {
    const shown = describeSidecarError(
      new Error("connect ECONNREFUSED 127.0.0.1:7860"),
    );
    assert.ok(
      !shown.includes("ECONNREFUSED"),
      `a newcomer would be shown: ${shown}`,
    );
    assert.ok(shown.length > 0);
    assert.ok(
      !describeSidecarError(new Error("connect ETIMEDOUT 1.2.3.4:80")).includes(
        "ETIMEDOUT",
      ),
    );
  });
});
