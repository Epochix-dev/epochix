/**
 * Settings the extension declares must do what they say.
 *
 * An audit of `contributes.configuration` against the code found three that
 * a user could change with nothing happening:
 *
 *   * `epochix.theme` — the panel had its own theme resolver that only ever
 *     followed VS Code, so "light" and "dark" were ignored.
 *   * `epochix.taskHint` — read into the config object and never passed to an
 *     engine; and the engine's task detection would have overwritten it anyway.
 *   * `epochix.llmFallback` — read and never used; the extension has no LLM
 *     path. It is now marked deprecated rather than pretending.
 *
 * And, on the way: saving a run to the sidecar sent its last metric TWICE, the
 * second copy carrying the "finished" flag on a new seq, so every persisted run
 * recorded its final epoch as two measurements.
 */
import * as assert from "assert";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";

import * as vscode from "vscode";

import { persistLogFile } from "../../sidecar/persistLog";
import type { ServerManager, SidecarEvent } from "../../sidecar/ServerManager";
import { DashboardPanel } from "../../webview/DashboardPanel";
import { StandaloneEngine } from "../../webview/StandaloneEngine";
import type { StoryFrameMsg } from "../../webview/messages";

const EXT_ID = "epochix.epochix";

const KERAS_ACC = Array.from(
  { length: 8 },
  (_, i) =>
    `Epoch ${i + 1}/8 - loss: ${(1.2 - i * 0.1).toFixed(4)} - accuracy: ${(0.5 + i * 0.05).toFixed(4)}` +
    ` - val_loss: ${(1.3 - i * 0.1).toFixed(4)} - val_accuracy: ${(0.48 + i * 0.05).toFixed(4)}`,
);

function framesFor(engine: StandaloneEngine, lines: string[]): StoryFrameMsg[] {
  const out: StoryFrameMsg[] = [];
  for (const line of lines) out.push(...engine.feed(line + "\n"));
  out.push(...engine.flush());
  assert.ok(out.length > 0, "no frames at all");
  return out;
}

async function setSetting(key: string, value: unknown): Promise<void> {
  await vscode.workspace
    .getConfiguration("epochix")
    .update(key, value, vscode.ConfigurationTarget.Global);
}

suite("Declared settings are honoured", () => {
  teardown(async () => {
    await setSetting("taskHint", undefined);
    await setSetting("theme", undefined);
    DashboardPanel.current?.dispose();
  });

  test("a pinned task survives task detection", () => {
    // Control: the same log, unpinned, is detected as classification — so the
    // pinned run below proves the hint changed something.
    const detected = framesFor(new StandaloneEngine(), KERAS_ACC);
    assert.ok(detected.every((f) => f.taskType === "classification"));

    const pinned = framesFor(new StandaloneEngine("segmentation"), KERAS_ACC);
    for (const f of pinned) {
      assert.strictEqual(f.taskType, "segmentation", "detection overwrote the pinned task");
    }
  });

  for (const theme of ["light", "dark"] as const) {
    test(`epochix.theme = ${theme} reaches the dashboard`, async () => {
      const ext = vscode.extensions.getExtension(EXT_ID);
      assert.ok(ext);
      await ext.activate();
      await setSetting("theme", theme);
      DashboardPanel.current?.dispose();

      const panel = DashboardPanel.createOrShow(ext.extensionUri, null, "en");
      const html = (panel as unknown as { _panel: vscode.WebviewPanel })._panel.webview.html;
      assert.ok(
        html.includes(`data-theme="${theme}"`),
        `the dashboard ignored epochix.theme=${theme}`,
      );
    });
  }

  test("saving a run to the sidecar sends each measurement once", async () => {
    await setSetting("taskHint", "segmentation");

    const created: Array<{ task: string | undefined }> = [];
    const events: SidecarEvent[] = [];
    const recorder = {
      port: 1,
      createRun: (_name: string, task?: string) => {
        created.push({ task });
        return Promise.resolve("run-1");
      },
      pushEvent: (_id: string, e: SidecarEvent) => {
        events.push(e);
        return Promise.resolve();
      },
    } as unknown as ServerManager;

    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "epochix-persist-"));
    const file = path.join(dir, "train.log");
    fs.writeFileSync(file, KERAS_ACC.join("\n") + "\n", "utf-8");

    await persistLogFile(recorder, file, "train.log");

    // The pinned task reaches the server's engine too.
    assert.deepStrictEqual(created, [{ task: "segmentation" }]);

    // Four metrics per epoch, eight epochs — and not one more.
    assert.strictEqual(events.length, 8 * 4, "an extra event was sent");
    const seqs = events.map((e) => e.seq);
    assert.strictEqual(new Set(seqs).size, seqs.length, "a seq was reused");
    const measurements = events.map((e) => `${e.epoch}|${e.canonical_key}`);
    assert.strictEqual(
      new Set(measurements).size,
      measurements.length,
      "the same measurement was sent twice",
    );

    // Exactly one event closes the run, and it is the last one sent — after
    // every batch, so the run cannot close before its data has arrived.
    const finished = events.filter((e) => e.finished);
    assert.strictEqual(finished.length, 1);
    assert.strictEqual(events[events.length - 1].finished, true);
    assert.strictEqual(events[events.length - 1].epoch, 8);
  });
});
