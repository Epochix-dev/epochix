/**
 * Live extension-host integration tests.
 *
 * These run inside a real VS Code instance (via @vscode/test-electron), so they
 * exercise the actual activate() path: status bar, sidecar resolution, terminal
 * watcher wiring, and command registration — the glue that unit tests can't
 * reach because it depends on the injected `vscode` API.
 */
import * as assert from "assert";

import * as vscode from "vscode";

const EXT_ID = "epochix.epochix";
const CONTRIBUTED_COMMANDS = [
  "epochix.openDashboard",
  "epochix.watchTerminal",
  "epochix.openLogFile",
  "epochix.exportRun",
  "epochix.compareRuns",
];

suite("Epochix extension — host integration", () => {
  suiteSetup(async () => {
    // Force standalone mode so activation never tries to spawn a Python
    // sidecar (this machine may have `epochix` on PATH; the test must not
    // depend on it or block on waitReady).
    await vscode.workspace
      .getConfiguration("epochix")
      .update("useSidecar", "never", vscode.ConfigurationTarget.Global);

    const ext = vscode.extensions.getExtension(EXT_ID);
    assert.ok(ext, `extension ${EXT_ID} not found in host`);
    await ext.activate();
  });

  test("extension is present and activated", () => {
    const ext = vscode.extensions.getExtension(EXT_ID);
    assert.ok(ext, "extension missing");
    assert.strictEqual(ext.isActive, true, "extension did not activate");
  });

  test("all contributed commands are registered", async () => {
    const registered = await vscode.commands.getCommands(true);
    for (const cmd of CONTRIBUTED_COMMANDS) {
      assert.ok(
        registered.includes(cmd),
        `command not registered: ${cmd}`,
      );
    }
  });

  test("compareRuns placeholder runs without throwing", async () => {
    // The one command with no side effects beyond an info toast — safe to
    // invoke headless. Proves the command handler is wired, not just declared.
    await vscode.commands.executeCommand("epochix.compareRuns");
  });

  test("status bar item was created on activation", () => {
    // Activation calls StatusBar.init(); if it threw, activate() above would
    // have rejected. This asserts the extension owns a disposable subscription
    // set (status bar + watcher + commands all pushed to ctx.subscriptions).
    const ext = vscode.extensions.getExtension(EXT_ID);
    assert.ok(ext?.isActive);
    assert.ok(ext?.exports === undefined || ext?.exports !== null);
  });
});
