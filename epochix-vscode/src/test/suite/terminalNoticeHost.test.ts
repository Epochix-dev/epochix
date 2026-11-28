/**
 * The notice, driven through the real TerminalWatcher in a real VS Code host:
 * the status-bar item it shows, the dashboard it opens, and the silence it
 * keeps for a command that is not training.
 *
 * The watcher reads a command through the shell-integration API, a
 * TerminalShellExecution whose read() yields the output as it arrives. A
 * recording is played through that same call, in chunks that split lines as
 * a terminal does, and the command ends when the stream does.
 */
import * as assert from "assert";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";

import * as vscode from "vscode";

import { NOTICE_COMMAND } from "../../terminal/notice";
import { TerminalWatcher } from "../../terminal/TerminalWatcher";
import { DashboardPanel } from "../../webview/DashboardPanel";
import type { StoryFrameMsg } from "../../webview/messages";
import { unreadLosses, unreadTable } from "./unreadLayout";

const EXT_ID = "epochix.epochix";

interface Watched {
  _consumeExecution(
    terminal: vscode.Terminal,
    execution: Pick<vscode.TerminalShellExecution, "read">,
  ): Promise<void>;
}

interface Inner {
  _engine: { snapshot: () => StoryFrameMsg[] } | null;
}

let made = 0;

async function setUp(
  timings: { quietMs?: number } = {},
): Promise<{ watcher: TerminalWatcher; terminal: vscode.Terminal; root: string }> {
  const ext = vscode.extensions.getExtension(EXT_ID);
  assert.ok(ext);
  await ext.activate();
  DashboardPanel.current?.dispose();
  const watcher = new TerminalWatcher(ext.extensionUri, "en", timings);
  const terminal = vscode.window.createTerminal({ name: `epochix notice ${++made}` });
  return { watcher, terminal, root: path.resolve(ext.extensionPath, "..") };
}

/** A command that prints `text` in chunks, then ends. */
function execution(text: string, n = 701): Pick<vscode.TerminalShellExecution, "read"> {
  return {
    read: async function* () {
      for (let i = 0; i < text.length; i += n) {
        yield text.slice(i, i + n);
        await new Promise((r) => setImmediate(r));
      }
    },
  };
}

async function play(watcher: TerminalWatcher, terminal: vscode.Terminal, file: string): Promise<void> {
  await playText(watcher, terminal, fs.readFileSync(file, "utf-8"));
}

async function playText(watcher: TerminalWatcher, terminal: vscode.Terminal, text: string): Promise<void> {
  await (watcher as unknown as Watched)._consumeExecution(terminal, execution(text));
}

/** A layout no reader takes (unreadLayout.ts), 20 tables of it: 80 lines. */
const UNREAD = unreadTable(20);

suite("The terminal notice in a real host", () => {
  const owned: vscode.Disposable[] = [];
  teardown(() => {
    DashboardPanel.current?.dispose();
    for (const d of owned.splice(0)) d.dispose();
  });

  test("a run in a layout nothing reads is said once, in the status bar", async () => {
    const { watcher, terminal } = await setUp();
    owned.push(watcher, terminal);
    await playText(watcher, terminal, UNREAD);

    assert.strictEqual(DashboardPanel.current, undefined, "a dashboard was opened");
    const shown = watcher.notice.shown;
    assert.ok(shown, "nothing was said");
    assert.strictEqual(shown.item.text, "$(question) Epochix: run not read");
    assert.strictEqual(shown.item.command, NOTICE_COMMAND);
    // The command the item runs is the activated extension's.
    assert.ok((await vscode.commands.getCommands(true)).includes(NOTICE_COMMAND));
    const said = shown.text.sentences;
    assert.ok(said.includes("The command printed 80 lines."), said.join(" "));
    assert.ok(said.some((s) => s.includes(`loss (${unreadLosses(20)} different values)`)), said.join(" "));
    // The tooltip says the same, sentence for sentence (escaped as Markdown).
    const tooltip = (shown.item.tooltip as vscode.MarkdownString).value.replace(/&nbsp;/g, " ");
    assert.ok(tooltip.includes("The command printed 80 lines."), tooltip);
    // No button: there is nothing the dashboard could show.
    watcher.notice.open();
    assert.strictEqual(DashboardPanel.current, undefined);
  });

  test("a Stable-Baselines3 run opens the dashboard and is not spoken of", async () => {
    const { watcher, terminal, root } = await setUp();
    owned.push(watcher, terminal);
    await play(watcher, terminal, path.join(root, "tests", "fixtures", "logs", "sb3_ppo_real.log"));

    const panel = DashboardPanel.current as unknown as Inner | undefined;
    assert.ok(panel?._engine, "a PPO run in a terminal opened no dashboard");
    assert.strictEqual(panel._engine.snapshot().length, 25, "the run was not told in full");
    assert.strictEqual(watcher.notice.shown, null, "a run the dashboard tells was spoken of");
  });

  test("a run the dashboard tells but never opened for can be opened", async () => {
    const { watcher, terminal, root } = await setUp();
    owned.push(watcher, terminal);
    await play(watcher, terminal, path.join(root, "tests", "fixtures", "logs", "catboost_real_classifier.log"));

    assert.strictEqual(DashboardPanel.current, undefined, "the premise: the feed did not recognise it");
    const shown = watcher.notice.shown;
    assert.ok(shown, "nothing was said");
    assert.strictEqual(shown.item.text, "$(graph) Epochix: run not opened");
    assert.ok(shown.text.canOpen);

    watcher.notice.open();
    const panel = DashboardPanel.current as unknown as Inner | undefined;
    assert.ok(panel?._engine, "opening it opened no dashboard");
    const frames = panel._engine.snapshot();
    assert.strictEqual(frames.length, 60, "the run was not told in full");
    assert.strictEqual(watcher.notice.shown, null, "the notice stood after it was acted on");
  });

  test("an ordinary command says nothing", async () => {
    const { watcher, terminal, root } = await setUp();
    owned.push(watcher, terminal);
    for (const name of ["git_log.log", "pip_install.log", "uvicorn_server.log", "npm_install.log"]) {
      await play(watcher, terminal, path.join(root, "tests", "fixtures", "terminal", name));
      assert.strictEqual(watcher.notice.shown, null, `${name} was spoken of`);
      assert.strictEqual(DashboardPanel.current, undefined, `${name} opened a dashboard`);
    }
  });

  test("a real shell's command reaches the notice through shell integration", async function () {
    this.timeout(90_000);
    const { watcher, terminal } = await setUp();
    owned.push(watcher, terminal);
    watcher.attachToActiveAutomatically();
    terminal.show();

    const integration =
      terminal.shellIntegration ??
      (await new Promise<vscode.TerminalShellIntegration | undefined>((resolve) => {
        const timer = setTimeout(() => resolve(undefined), 30_000);
        const sub = vscode.window.onDidChangeTerminalShellIntegration((e) => {
          if (e.terminal !== terminal) return;
          clearTimeout(timer);
          sub.dispose();
          resolve(e.shellIntegration);
        });
      }));
    assert.ok(integration, "shell integration never activated in the test terminal");

    const log = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "epochix-notice-")), "unread.log");
    fs.writeFileSync(log, UNREAD, "utf-8");
    const quoted = `'${log.replace(/'/g, "''")}'`;
    integration.executeCommand(
      process.platform === "win32" ? `Get-Content -Raw ${quoted}` : `cat ${quoted}`,
    );
    const deadline = Date.now() + 45_000;
    while (watcher.notice.shown === null && Date.now() < deadline) {
      await new Promise((r) => setTimeout(r, 250));
    }
    const shown = watcher.notice.shown;
    assert.ok(shown, "the command was never judged");
    assert.strictEqual(shown.item.text, "$(question) Epochix: run not read");
    assert.ok(shown.text.sentences.some((s) => s.includes("loss")), shown.text.sentences.join(" "));
  });

  test("a recognised run withdraws what was said while it was not", async () => {
    const { watcher: quick, terminal } = await setUp({ quietMs: 50 });
    owned.push(quick, terminal);
    const unread = UNREAD;
    let epochs = "";
    for (let e = 1; e <= 4; e++) {
      epochs += `Epoch ${e}/4\n100/100 - 2s - loss: ${(2 - e * 0.3).toFixed(3)} - val_accuracy: ${(0.5 + e * 0.1).toFixed(3)}\n`;
    }
    // A long run in an unread layout, judged while it runs, that then prints
    // lines the feed recognises.
    let release!: () => void;
    const pause = new Promise<void>((r) => (release = r));
    const stream: Pick<vscode.TerminalShellExecution, "read"> = {
      read: async function* () {
        yield unread;
        await pause;
        yield epochs;
      },
    };
    const done = (quick as unknown as Watched)._consumeExecution(terminal, stream);
    await new Promise((r) => setTimeout(r, 400));
    assert.ok(quick.notice.shown, "a quiet command was not judged");
    release();
    await done;
    assert.ok(DashboardPanel.current, "the recognised lines opened no dashboard");
    assert.strictEqual(quick.notice.shown, null, "the notice stood once the run was recognised");
  });
});

