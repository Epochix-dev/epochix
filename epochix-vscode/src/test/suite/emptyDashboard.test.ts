/**
 * A dashboard opened with nothing attached explains itself (issue #35).
 *
 * The panel told the webview it was "live" whatever fed it, so a bare panel
 * read "Waiting for training data…" forever — a user's bug report showed just
 * that and "epochs 0". The panel now says whether anything feeds it, and the
 * webview offers the ways in as buttons, which may run only those commands.
 */
import * as assert from "assert";

import * as vscode from "vscode";

import { ALLOWED_WEBVIEW_COMMANDS, DashboardPanel } from "../../webview/DashboardPanel";
import type { ExtToWeb, WebToExt } from "../../webview/messages";

const EXT_ID = "epochix.epochix";

interface Inner {
  _attached: boolean;
  _handleWebMessage(msg: WebToExt): void;
  _post(msg: ExtToWeb): void;
}

async function bare(): Promise<Inner> {
  const ext = vscode.extensions.getExtension(EXT_ID);
  assert.ok(ext);
  await ext.activate();
  DashboardPanel.current?.dispose();
  return DashboardPanel.createOrShow(ext.extensionUri, null, "en") as unknown as Inner;
}

suite("The empty dashboard", () => {
  teardown(() => DashboardPanel.current?.dispose());

  test("a bare panel says nothing is attached", async () => {
    const panel = await bare();
    const sent: ExtToWeb[] = [];
    panel._post = (m) => void sent.push(m);
    panel._handleWebMessage({ type: "ready" });
    const init = sent.find((m) => m.type === "init");
    assert.ok(init && init.type === "init");
    assert.strictEqual(init.attached, false);
  });

  test("terminal output attaches it", async () => {
    const panel = await bare();
    (panel as unknown as DashboardPanel).feedLines("epoch=1 loss=0.5\n");
    assert.strictEqual(panel._attached, true);
  });

  test("only the empty-state commands may be run from the webview", async () => {
    let ran = false;
    const probe = vscode.commands.registerCommand("epochix.test.notAllowed", () => {
      ran = true;
    });
    try {
      const panel = await bare();
      panel._handleWebMessage({ type: "runCommand", command: "epochix.test.notAllowed" });
      await new Promise((r) => setTimeout(r, 200));
      assert.strictEqual(ran, false, "a webview message ran an arbitrary command");
    } finally {
      probe.dispose();
    }
    assert.deepStrictEqual(
      [...ALLOWED_WEBVIEW_COMMANDS].sort(),
      ["epochix.openLogFile", "epochix.tryDemo", "epochix.watchTerminal"],
    );
  });

  test("an allowed button runs its command", async () => {
    // The host runs the bundled extension, a separate copy of DashboardPanel
    // from the one imported here, so the relay is observed at the VS Code API
    // this copy calls rather than through the bundle's panel.
    const ran: string[] = [];
    const real = vscode.commands.executeCommand;
    (vscode.commands as { executeCommand: unknown }).executeCommand = (c: string) => {
      ran.push(c);
      return Promise.resolve(undefined);
    };
    try {
      const panel = await bare();
      for (const c of ALLOWED_WEBVIEW_COMMANDS) {
        panel._handleWebMessage({ type: "runCommand", command: c });
      }
    } finally {
      (vscode.commands as { executeCommand: unknown }).executeCommand = real;
    }
    assert.deepStrictEqual(ran, [...ALLOWED_WEBVIEW_COMMANDS]);
  });

  test("what the demo button runs attaches the panel and tells a story", async () => {
    // epochix.tryDemo is DashboardPanel.openLog on the bundled demo log.
    const ext = vscode.extensions.getExtension(EXT_ID);
    assert.ok(ext);
    await ext.activate();
    DashboardPanel.current?.dispose();
    const demo = vscode.Uri.joinPath(ext.extensionUri, "media", "demo.log");
    DashboardPanel.openLog(ext.extensionUri, demo, null, "en");
    await new Promise((r) => setTimeout(r, 2500));
    const panel = DashboardPanel.current as unknown as Inner & {
      _engine: { snapshot: () => unknown[] } | null;
    };
    assert.ok(panel, "no panel was opened");
    assert.strictEqual(panel._attached, true);
    const sent: ExtToWeb[] = [];
    panel._post = (m) => void sent.push(m);
    panel._handleWebMessage({ type: "ready" });
    const init = sent.find((m) => m.type === "init");
    assert.ok(init && init.type === "init" && init.attached === true);
    assert.ok(panel._engine && panel._engine.snapshot().length > 0, "the demo produced no frames");
  });
});
