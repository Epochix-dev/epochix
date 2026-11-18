/**
 * A pytest run in a watched terminal opens no dashboard and tells no story.
 *
 * A recorded `pytest -v` of four tests named after metrics, one failing on
 * `val_loss = 0.42` (tests/fixtures/terminal/pytest.log), scored 0.60 on the
 * detector — `learning_rate` and `precision` in its test ids, `val_loss = 0.42`
 * in the failing test's source — and opened the dashboard, which told one
 * reading of `val_loss` taken from that source. The parser side is held to
 * Python by parsers.golden.json (tests/integration/test_pytest_output.py);
 * this drives the detector and the engine on the recording itself.
 */
import * as assert from "assert";
import * as fs from "fs";
import * as path from "path";

import * as vscode from "vscode";

import { withoutTestReport } from "../../parsers/pytestReport";
import { TerminalFeed } from "../../terminal/TerminalFeed";
import { isTraining, sniff } from "../../terminal/TrainingDetector";
import { StandaloneEngine } from "../../webview/StandaloneEngine";

const EXT_ID = "epochix.epochix";

function repoRoot(): string {
  const ext = vscode.extensions.getExtension(EXT_ID);
  assert.ok(ext, `extension ${EXT_ID} not found`);
  return path.resolve(ext.extensionPath, "..");
}

function pytestLog(): string {
  const text = fs.readFileSync(path.join(repoRoot(), "tests", "fixtures", "terminal", "pytest.log"), "utf-8");
  assert.ok(text.includes("        val_loss = 0.42"), "the recording no longer shows the premise");
  assert.ok(text.includes("::test_learning_rate_schedule_decays PASSED"));
  return text;
}

suite("pytest output", () => {
  test("a recorded pytest run does not open the dashboard", () => {
    const text = pytestLog();
    for (const n of [1, 64, 512, text.length]) {
      const feed = new TerminalFeed();
      for (let i = 0; i < text.length; i += n) {
        assert.strictEqual(feed.push(text.slice(i, i + n)), null, `opened (chunks of ${n})`);
      }
      assert.strictEqual(feed.detected, false);
    }
    assert.strictEqual(sniff(text), 0);
  });

  test("the engine tells nothing from it", () => {
    const engine = new StandaloneEngine();
    const frames = [...engine.feed(pytestLog()), ...engine.flush()];
    assert.deepStrictEqual(frames, []);
    assert.deepStrictEqual(engine.metrics(), []);
  });

  test("only the report and the test ids are left out of the score", () => {
    const text = pytestLog();
    const kept = withoutTestReport(text);
    assert.ok(!kept.includes("val_loss = 0.42"), "the failing test's source was scored");
    assert.ok(!kept.includes("test_learning_rate"), "a test id was scored");
    assert.ok(kept.includes("short test summary info"), "the report's end was not found");
    assert.ok(kept.includes("1 failed, 3 passed"));
  });

  test("training output is scored as before", () => {
    // Every line a run prints survives, a rule of equals signs included.
    let log = "=".repeat(40) + "\n";
    for (let e = 1; e <= 3; e++) log += `Epoch ${e}/3 train_loss=${(2 - e * 0.3).toFixed(3)} val_accuracy=${(0.5 + e * 0.1).toFixed(3)}\n`;
    assert.strictEqual(withoutTestReport(log), log);
    assert.ok(isTraining(log));
    // And a run printed by a passing test is still a run: only a failure's
    // report is left out.
    const underTest = "tests/test_train.py::test_fit PASSED\n" + log;
    assert.ok(isTraining(underTest));
  });
});
