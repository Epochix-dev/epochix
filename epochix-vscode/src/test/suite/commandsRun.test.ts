/**
 * Every contributed command, run the way a user runs it.
 *
 * Six of the eight were registered, listed in the palette and never once run
 * by a test. One of them could not have worked: "Epochix: Export Run" posted a
 * `requestExport` message that nothing in the webview, the server or the panel
 * handled, so after a format was picked nothing happened, every time.
 *
 * The host runs the bundled extension, a separate copy of DashboardPanel from
 * the one a test imports, so each command is run through executeCommand and
 * observed at the VS Code API it calls (the same module object the bundle
 * uses), and its panel through the editor tabs.
 */
import * as assert from "assert";
import * as os from "os";
import * as path from "path";

import * as vscode from "vscode";

const EXT_ID = "epochix.epochix";

/** Replace `obj[key]` for one test; returns the restore. */
function stub<T extends object, K extends keyof T>(obj: T, key: K, fn: unknown): () => void {
  const real = obj[key];
  (obj as Record<K, unknown>)[key] = fn;
  return () => {
    (obj as Record<K, unknown>)[key] = real;
  };
}

/** Collect the messages one `vscode.window.show*Message` shows, answering `reply`. */
function messages(kind: "showInformationMessage" | "showWarningMessage", reply?: string) {
  const shown: string[] = [];
  const restore = stub(vscode.window, kind, (text: string) => {
    shown.push(text);
    return Promise.resolve(reply);
  });
  return { shown, restore };
}

function opened(): { urls: string[]; restore: () => void } {
  const urls: string[] = [];
  const restore = stub(vscode.env, "openExternal", (target: unknown) => {
    urls.push(String(target));
    return Promise.resolve(true);
  });
  return { urls, restore };
}

function epochixTabs(): vscode.Tab[] {
  return vscode.window.tabGroups.all
    .flatMap((g) => g.tabs)
    .filter((t) => t.input instanceof vscode.TabInputWebview && t.label === "Epochix");
}

async function until(check: () => boolean, ms = 4000): Promise<boolean> {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    if (check()) return true;
    await new Promise((r) => setTimeout(r, 50));
  }
  return check();
}

const settle = (): Promise<void> => new Promise((r) => setTimeout(r, 300));

function repoLog(name: string): vscode.Uri {
  const ext = vscode.extensions.getExtension(EXT_ID);
  assert.ok(ext);
  return vscode.Uri.file(path.join(ext.extensionPath, "..", "tests", "fixtures", "logs", name));
}

suite("Every command, run", () => {
  suiteSetup(async () => {
    // Standalone, as the rest of the suite: no Python engine is started.
    await vscode.workspace
      .getConfiguration("epochix")
      .update("useSidecar", "never", vscode.ConfigurationTarget.Global);
    const ext = vscode.extensions.getExtension(EXT_ID);
    assert.ok(ext);
    await ext.activate();
  });

  setup(async () => {
    await vscode.commands.executeCommand("workbench.action.closeAllEditors");
    await settle();
  });

  teardown(() => vscode.commands.executeCommand("workbench.action.closeAllEditors"));

  test("Export Run with no run open says so", async () => {
    const warn = messages("showWarningMessage");
    try {
      await vscode.commands.executeCommand("epochix.exportRun");
    } finally {
      warn.restore();
    }
    assert.deepStrictEqual(warn.shown, ["Epochix: No active run to export. Open a log file first."]);
  });

  test("Export Run on an open run answers the format picked", async () => {
    await vscode.commands.executeCommand("epochix.openLogFile", repoLog("keras_50ep.log"));
    assert.ok(await until(() => epochixTabs().length === 1), "the log opened no panel");

    const offered: string[] = [];
    const restorePick = stub(vscode.window, "showQuickPick", async (items: unknown) => {
      const list = (await items) as { id: string }[];
      offered.push(...list.map((i) => i.id));
      return list.find((i) => i.id === "md");
    });
    const info = messages("showInformationMessage");
    try {
      await vscode.commands.executeCommand("epochix.exportRun");
      await until(() => info.shown.length > 0, 1500);
    } finally {
      restorePick();
      info.restore();
    }
    assert.deepStrictEqual(offered, ["html", "pdf", "md"]);
    // Standalone: the built-in engine says why it writes no file. It said
    // nothing at all before.
    assert.strictEqual(info.shown.length, 1, JSON.stringify(info.shown));
    assert.match(info.shown[0], /export needs the Python engine/);
  });

  test("Open Log File asks for a file, and opens nothing when none is chosen", async () => {
    let restore = stub(vscode.window, "showOpenDialog", () => Promise.resolve(undefined));
    try {
      await vscode.commands.executeCommand("epochix.openLogFile");
      await settle();
    } finally {
      restore();
    }
    assert.strictEqual(epochixTabs().length, 0, "a cancelled dialog opened a panel");

    restore = stub(vscode.window, "showOpenDialog", () =>
      Promise.resolve([repoLog("keras_short.log")]),
    );
    try {
      await vscode.commands.executeCommand("epochix.openLogFile");
    } finally {
      restore();
    }
    assert.ok(await until(() => epochixTabs().length === 1), "the chosen log opened no panel");
  });

  test("Open Dashboard opens one panel, and again brings back the same one", async () => {
    await vscode.commands.executeCommand("epochix.openDashboard");
    assert.ok(await until(() => epochixTabs().length === 1), "no panel opened");
    await vscode.commands.executeCommand("epochix.openDashboard");
    await settle();
    assert.strictEqual(epochixTabs().length, 1);
  });

  test("Open in Browser without the Python engine says what it needs", async () => {
    const info = messages("showInformationMessage", "Install instructions");
    const ext = opened();
    try {
      await vscode.commands.executeCommand("epochix.openInBrowser");
      await until(() => ext.urls.length > 0, 1500);
    } finally {
      info.restore();
      ext.restore();
    }
    assert.strictEqual(info.shown.length, 1);
    assert.match(info.shown[0], /needs the Python engine/);
    assert.deepStrictEqual(ext.urls, ["https://github.com/epochix-dev/epochix#install"]);
  });

  test("Report a Bug opens an issue that names versions and nothing of the user's", async () => {
    const ext = opened();
    try {
      await vscode.commands.executeCommand("epochix.reportBug");
    } finally {
      ext.restore();
    }
    assert.strictEqual(ext.urls.length, 1);
    const url = new URL(ext.urls[0]);
    assert.strictEqual(url.origin + url.pathname, "https://github.com/Epochix-dev/epochix/issues/new");
    assert.strictEqual(url.searchParams.get("labels"), "bug");
    const body = url.searchParams.get("body") ?? "";
    const version = (vscode.extensions.getExtension(EXT_ID)?.packageJSON as { version: string })
      .version;
    assert.ok(body.includes(`extension    ${version}`), body);
    assert.ok(body.includes(`vscode       ${vscode.version}`), body);
    assert.ok(body.includes("python pkg   not reachable (standalone mode)"), body);
    assert.ok(!body.includes(os.homedir()), "the report carries the user's home folder");
  });

  test("Watch Terminal with no terminal says so, and with one names it", async () => {
    for (const t of vscode.window.terminals) t.dispose();
    await until(() => vscode.window.activeTerminal === undefined);
    const warn = messages("showWarningMessage");
    try {
      await vscode.commands.executeCommand("epochix.watchTerminal");
    } finally {
      warn.restore();
    }
    assert.deepStrictEqual(warn.shown, ["Epochix: No active terminal found."]);

    const terminal = vscode.window.createTerminal("epochix-watch-test");
    terminal.show();
    try {
      assert.ok(await until(() => vscode.window.activeTerminal === terminal), "terminal not active");
      const info = messages("showInformationMessage");
      const warned = messages("showWarningMessage");
      // Another suite's terminal can take focus as it closes: the command
      // reads whichever is active when it runs, and must name that one.
      let active: string | undefined;
      try {
        active = vscode.window.activeTerminal?.name;
        await vscode.commands.executeCommand("epochix.watchTerminal");
      } finally {
        info.restore();
        warned.restore();
      }
      // Watching, or why it cannot yet: shell integration may not be up in a
      // terminal this new. Either way the user is told, naming the terminal.
      const said = [...info.shown, ...warned.shown];
      assert.strictEqual(said.length, 1, JSON.stringify(said));
      assert.ok(active, "no terminal was active");
      assert.ok(said[0].includes(`"${active}"`), said[0]);
    } finally {
      terminal.dispose();
    }
  });
});
