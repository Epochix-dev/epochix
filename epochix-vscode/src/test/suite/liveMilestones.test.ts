/**
 * A watched run's milestones and warnings reach the panel as they arise.
 *
 * The panel sent them only inside `init`, which goes out when the webview
 * first loads. A terminal run opens the panel before it has printed much, so
 * every milestone and warning after that never reached the timeline or the
 * warning strip, and nor did the milestones a run ends with. Driven through
 * the real panel and engine: terminal text in, the posted messages out.
 */
import * as assert from "assert";
import * as fs from "fs";
import * as path from "path";

import * as vscode from "vscode";

import { DashboardPanel } from "../../webview/DashboardPanel";
import { StandaloneEngine } from "../../webview/StandaloneEngine";
import type { ExtToWeb, WebToExt } from "../../webview/messages";

const EXT_ID = "epochix.epochix";

interface Inner {
  _handleWebMessage(msg: WebToExt): void;
  _post(msg: ExtToWeb): void;
}

async function opened(): Promise<{ panel: DashboardPanel; sent: ExtToWeb[] }> {
  const ext = vscode.extensions.getExtension(EXT_ID);
  assert.ok(ext);
  await ext.activate();
  DashboardPanel.current?.dispose();
  const panel = DashboardPanel.createOrShow(ext.extensionUri, null, "en");
  const inner = panel as unknown as Inner;
  const sent: ExtToWeb[] = [];
  inner._post = (m) => void sent.push(m);
  // The webview loads before the run has printed anything.
  inner._handleWebMessage({ type: "ready" });
  return { panel, sent };
}

// A terminal goes quiet between epochs; the panel then reads what has come
// (DashboardPanel's IDLE_SETTLE_MS is 1.5 s). Until then a run shorter than
// the parser sniff draws nothing at all.
const quiet = (): Promise<void> => new Promise((r) => setTimeout(r, 2000));

/** The first `n` lines of a log, and the rest. */
function split(text: string, n: number): [string, string] {
  const lines = text.split("\n");
  return [lines.slice(0, n).join("\n") + "\n", lines.slice(n).join("\n")];
}

function chunks(text: string, n: number): string[] {
  const out: string[] = [];
  for (let i = 0; i < text.length; i += n) out.push(text.slice(i, i + n));
  return out;
}

function log(name: string): string {
  const ext = vscode.extensions.getExtension(EXT_ID);
  assert.ok(ext);
  return fs.readFileSync(
    path.join(ext.extensionPath, "..", "tests", "fixtures", "logs", name), "utf-8");
}

/** What the engine itself holds for the same text, read in one go. */
function told(text: string): StandaloneEngine {
  const engine = new StandaloneEngine();
  engine.feed(text);
  engine.flush();
  engine.finish();
  return engine;
}

suite("A watched run's milestones and warnings", () => {
  teardown(() => DashboardPanel.current?.dispose());

  test("each milestone is posted once, the run's last ones included", async function () {
    this.timeout(10000);
    const text = log("keras_50ep.log");
    const { panel, sent } = await opened();
    const init = sent.find((m) => m.type === "init");
    assert.ok(init && init.type === "init" && init.milestones.length === 0);

    const [first, rest] = split(text, 60);
    for (const chunk of chunks(first, 700)) panel.feedLines(chunk);
    await quiet();
    const midRun = sent.filter((m) => m.type === "milestone").length;
    assert.ok(midRun > 0, "no milestone reached the panel while the run was going");
    for (const chunk of chunks(rest, 700)) panel.feedLines(chunk);
    panel.endOfStream();

    const posted = sent.flatMap((m) => (m.type === "milestone" ? [m.milestone] : []));
    const want = told(text).milestones();
    assert.ok(want.some((m) => m.kind === "biggest_jump"), JSON.stringify(want));
    const key = (m: { seq: number; kind: string }): string => `${m.seq}|${m.kind}`;
    assert.deepStrictEqual(posted.map(key).sort(), want.map(key).sort());
    assert.strictEqual(new Set(posted.map(key)).size, posted.length, "a milestone posted twice");
    // The run's own end arrives before the summary that closes the panel's run.
    const order = sent.map((m) => m.type);
    assert.ok(order.lastIndexOf("milestone") < order.indexOf("complete"), order.join(","));
  });

  test("each warning the run raises is posted, once", async () => {
    const text = log("plateau.log");
    const want = told(text).warnings();
    assert.ok(want.length > 0, "the fixture raises no warning");
    const { panel, sent } = await opened();
    for (const chunk of chunks(text, 300)) panel.feedLines(chunk);
    panel.endOfStream();
    const posted = sent.flatMap((m) => (m.type === "warning" ? [m.warning] : []));
    assert.deepStrictEqual(posted, want);
  });

  test("a panel that reloads mid-run is not sent them again", async function () {
    this.timeout(10000);
    const text = log("keras_50ep.log");
    const { panel, sent } = await opened();
    const [first, rest] = split(text, 60);
    panel.feedLines(first);
    await quiet();
    // A second ready handshake (a reload): init carries all so far.
    (panel as unknown as Inner)._handleWebMessage({ type: "ready" });
    const inits = sent.filter((m) => m.type === "init");
    const carried = inits[inits.length - 1];
    assert.ok(carried.type === "init" && carried.milestones.length > 0);
    const before = sent.length;
    panel.feedLines(rest);
    panel.endOfStream();
    const after = sent.slice(before).flatMap((m) => (m.type === "milestone" ? [m.milestone] : []));
    const inInit = new Set(carried.milestones.map((m) => `${m.seq}|${m.kind}`));
    for (const m of after) assert.ok(!inInit.has(`${m.seq}|${m.kind}`), `re-sent ${m.kind}`);
    assert.ok(after.some((m) => m.kind === "training_complete"));
  });
});
