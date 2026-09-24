/**
 * The extension's engine must read metric names exactly as the Python engine.
 *
 * Its tables were hand-ported and drifted: a differential run over 319 names
 * found 170 canonicalised differently. `valid_loss` and `eval_loss` became
 * TRAINING loss here; a Keras regression's `mae` and `val_mae` merged into
 * one "MAE" series, so the run was graded on a mix of the error it trained on
 * and the error it was tested on.
 *
 * The tables are now generated from the Python source, and
 * `canonical.golden.json` holds Python's answer for 375 names —
 * `tests/unit/test_ts_engine_tables_sync.py` keeps both current on that side.
 */
import * as assert from "assert";
import * as fs from "fs";
import * as path from "path";

import * as vscode from "vscode";

import { StandaloneEngine, _internals } from "../../webview/StandaloneEngine";
import type { StoryFrameMsg } from "../../webview/messages";

const EXT_ID = "epochix.epochix";

function golden(): Record<string, string> {
  const ext = vscode.extensions.getExtension(EXT_ID);
  assert.ok(ext, `extension ${EXT_ID} not found`);
  const file = path.join(ext.extensionPath, "src", "test", "fixtures", "canonical.golden.json");
  return JSON.parse(fs.readFileSync(file, "utf-8")) as Record<string, string>;
}

function drive(lines: string[]): { frames: StoryFrameMsg[]; engine: StandaloneEngine } {
  const engine = new StandaloneEngine();
  const frames: StoryFrameMsg[] = [];
  for (const line of lines) frames.push(...engine.feed(line + "\n"));
  frames.push(...engine.flush());
  assert.ok(frames.length > 0, "no story at all");
  return { frames, engine };
}

suite("Engine parity with Python", () => {
  test("every name canonicalises as the Python engine does", () => {
    const expected = golden();
    const names = Object.keys(expected);
    assert.ok(names.length > 300, `golden file is nearly empty (${names.length})`);
    const wrong = names
      .filter((n) => _internals.canonicalise(n) !== expected[n])
      .map((n) => `${n}: python=${expected[n]} extension=${_internals.canonicalise(n)}`);
    assert.deepStrictEqual(wrong, []);
  });

  test("a Keras regression is graded on its validation error, not its training error", () => {
    // Training error keeps falling; validation error bottoms out and rises —
    // the overfitting a story exists to call out.
    const train = [2.0, 1.4, 1.0, 0.7, 0.5, 0.35, 0.25, 0.18];
    const val = [2.1, 1.6, 1.3, 1.2, 1.25, 1.35, 1.5, 1.7];
    const lines = train.map(
      (t, i) =>
        `Epoch ${i + 1}/8 - loss: ${(t * t).toFixed(4)} - mae: ${t.toFixed(4)}` +
        ` - val_loss: ${(val[i] * val[i]).toFixed(4)} - val_mae: ${val[i].toFixed(4)}`,
    );
    const { frames, engine } = drive(lines);
    assert.strictEqual(engine.primaryMetricKey(), "val_MAE", "graded on the wrong series");
    assert.deepStrictEqual(
      frames.map((f) => f.primaryMetricValue),
      val,
      "the graded series is not the validation error the log printed",
    );
  });

  test("valid_loss is validation loss", () => {
    const lines = [0.9, 0.7, 0.6, 0.55, 0.52].map(
      (v, i) => `epoch ${i + 1} train_loss=${(v * 0.8).toFixed(3)} valid_loss=${v.toFixed(3)}`,
    );
    const { frames, engine } = drive(lines);
    assert.strictEqual(engine.primaryMetricKey(), "val_loss");
    assert.deepStrictEqual(frames.map((f) => f.primaryMetricValue), [0.9, 0.7, 0.6, 0.55, 0.52]);
  });
});
