/**
 * A watched terminal that goes quiet gets its story, without waiting for the
 * run to end.
 *
 * The engine samples up to 200 lines before choosing a parser, as the Python
 * pipeline does — choosing on six lines picked parsers from a banner or a model
 * summary. A live run shorter than that would then draw nothing until it
 * ended; the panel settles on what has arrived once the terminal is quiet for
 * a moment (Python's IDLE_SNIFF_SECS). This drives the real panel.
 */
import * as assert from "assert";

import * as vscode from "vscode";

import { DashboardPanel } from "../../webview/DashboardPanel";
import type { StoryFrameMsg } from "../../webview/messages";

const EXT_ID = "epochix.epochix";

suite("A quiet terminal is settled", () => {
  teardown(() => DashboardPanel.current?.dispose());

  test("the panel settles a quiet terminal", async () => {
    const ext = vscode.extensions.getExtension(EXT_ID);
    assert.ok(ext);
    await ext.activate();
    DashboardPanel.current?.dispose();
    const panel = DashboardPanel.createOrShow(ext.extensionUri, null, "en");
    const inner = panel as unknown as { _engine: { snapshot: () => StoryFrameMsg[] } | null };
    assert.ok(inner._engine, "standalone panel has no engine");

    let log = "";
    for (let e = 1; e <= 5; e++) {
      log += `epoch=${e} train_loss=${(2 - e * 0.2).toFixed(3)} val_accuracy=${(0.5 + e * 0.05).toFixed(3)}\n`;
    }
    panel.feedLines(log);
    assert.strictEqual(inner._engine.snapshot().length, 0, "chose a parser on five lines");

    await new Promise((r) => setTimeout(r, 2000)); // past the 1.5 s quiet period
    const frames = inner._engine.snapshot();
    assert.strictEqual(frames.length, 5, "the quiet terminal was never settled");
    assert.deepStrictEqual(frames.map((f) => f.epoch), [1, 2, 3, 4, 5]);
  });
});
