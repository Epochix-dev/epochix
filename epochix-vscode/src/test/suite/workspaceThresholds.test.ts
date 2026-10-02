/**
 * The panel grades with a workspace's `.epochix.yaml` — mirrors
 * tests/integration/test_custom_thresholds_e2e.py.
 *
 * The command line read the file and the extension's engine did not, so a
 * workspace with custom thresholds showed one grade in the panel and another
 * from `epochix run`. These go the whole way: a file on disk, found from a
 * folder, read, and handed to the engine that tells the run.
 */
import * as assert from "assert";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";

import { findGradeConfigFile, readGradeConfigFile } from "../../gradeConfigFile";
import { StandaloneEngine } from "../../webview/StandaloneEngine";

// Anything under 99.5% accuracy is an F: nothing a real run reaches by accident.
const STRICT = [
  "version: 1",
  "grade_thresholds:",
  "  classification:",
  '    "A+": 0.999',
  "    A: 0.998",
  "    B: 0.997",
  "    C: 0.996",
  "    D: 0.995",
  "    F: 0.0",
  "",
].join("\n");

const ACCURACY = [0.58, 0.66, 0.74, 0.82, 0.9];

function accuracyLog(): string {
  return (
    ACCURACY.map(
      (v, i) => `Epoch ${i + 1}/5 train_loss=${(1 / (i + 1)).toFixed(3)} val_accuracy=${v}`,
    ).join("\n") + "\n"
  );
}

function told(text: string, configFile: string | null): StandaloneEngine {
  const config = configFile === null ? null : readGradeConfigFile(configFile);
  const engine = new StandaloneEngine(undefined, "en", config);
  engine.feed(text);
  engine.flush();
  return engine;
}

suite("The panel grades with the workspace's thresholds", () => {
  let project: string;

  setup(() => {
    project = fs.mkdtempSync(path.join(os.tmpdir(), "epochix-thresholds-"));
  });

  teardown(() => {
    fs.rmSync(project, { recursive: true, force: true });
  });

  test("a file in the workspace changes the grade", () => {
    const before = told(accuracyLog(), null).snapshot();
    assert.strictEqual(before[before.length - 1].grade, "A", "premise: 90% is an A built in");

    fs.writeFileSync(path.join(project, ".epochix.yaml"), STRICT, "utf8");
    const found = findGradeConfigFile(project, undefined);
    assert.strictEqual(found, path.join(project, ".epochix.yaml"));
    const after = told(accuracyLog(), found).snapshot();
    assert.strictEqual(after[after.length - 1].primaryMetricValue, 0.9);
    assert.deepStrictEqual([...new Set(after.map((f) => f.grade))], ["F"]);
    assert.deepStrictEqual([...new Set(after.map((f) => f.gradeBasis))], ["thresholds"]);
  });

  test("it is found from a folder below it, and from the per-user folder", () => {
    fs.writeFileSync(path.join(project, ".epochix.yaml"), STRICT, "utf8");
    const nested = path.join(project, "experiments", "run7");
    fs.mkdirSync(nested, { recursive: true });
    assert.strictEqual(findGradeConfigFile(nested, undefined), path.join(project, ".epochix.yaml"));

    const home = fs.mkdtempSync(path.join(os.tmpdir(), "epochix-home-"));
    try {
      fs.mkdirSync(path.join(home, ".epochix"));
      const perUser = path.join(home, ".epochix", ".epochix.yaml");
      fs.writeFileSync(perUser, STRICT, "utf8");
      const elsewhere = fs.mkdtempSync(path.join(os.tmpdir(), "epochix-elsewhere-"));
      try {
        assert.strictEqual(findGradeConfigFile(elsewhere, home), perUser);
        assert.strictEqual(findGradeConfigFile(undefined, home), perUser);
        // The nearer file wins over the per-user one.
        assert.strictEqual(findGradeConfigFile(nested, home), path.join(project, ".epochix.yaml"));
      } finally {
        fs.rmSync(elsewhere, { recursive: true, force: true });
      }
    } finally {
      fs.rmSync(home, { recursive: true, force: true });
    }
  });

  test("no file, no home: the built-in thresholds", () => {
    assert.strictEqual(findGradeConfigFile(project, undefined), null);
    assert.strictEqual(findGradeConfigFile(undefined, undefined), null);
  });

  test("a task's entry does not touch the task's other metrics", () => {
    fs.writeFileSync(path.join(project, ".epochix.yaml"), STRICT, "utf8");
    const file = path.join(project, ".epochix.yaml");
    const auc = [0.95, 0.96, 0.97, 0.98, 0.984]
      .map((v, i) => `Epoch ${i + 1}/5 val_auc=${v}`)
      .join("\n");
    const frames = told(auc + "\n", file).snapshot();
    assert.strictEqual(frames[frames.length - 1].primaryMetric, "val_AUC");
    assert.strictEqual(frames[frames.length - 1].grade, "A+");
  });

  test("a regression entry grades the error, not R2", () => {
    const file = path.join(project, ".epochix.yaml");
    fs.writeFileSync(
      file,
      "grade_thresholds:\n  regression:\n    A: 1.0\n    B: 2.5\n    C: 5.0\n    D: 10.0\n    F: .inf\n",
      "utf8",
    );
    const r2 = [0.9, 0.95, 0.97, 0.98, 0.99].map((v, i) => `Epoch ${i + 1}/5 val_r2=${v}`);
    const r2Frames = told(r2.join("\n") + "\n", file).snapshot();
    assert.strictEqual(r2Frames[r2Frames.length - 1].grade, "A+");

    const mae = [9.0, 7.0, 5.5, 4.0, 3.0].map((v, i) => `Epoch ${i + 1}/5 val_mae=${v}`);
    const maeFrames = told(mae.join("\n") + "\n", file).snapshot();
    assert.strictEqual(maeFrames[maeFrames.length - 1].primaryMetric, "val_MAE");
    // 3.0 is over B's 2.5 and within C's 5.0; the bands rise, so lower is better.
    assert.strictEqual(maeFrames[maeFrames.length - 1].grade, "C");
    assert.strictEqual(maeFrames[maeFrames.length - 1].gradeBasis, "thresholds");
  });

  test("a file that cannot be read leaves the built-in thresholds", () => {
    const file = path.join(project, ".epochix.yaml");
    fs.writeFileSync(file, "grade_thresholds: [unclosed\n", "utf8");
    assert.strictEqual(readGradeConfigFile(file), null);
    assert.strictEqual(readGradeConfigFile(path.join(project, "missing.yaml")), null);
    const frames = told(accuracyLog(), file).snapshot();
    assert.strictEqual(frames[frames.length - 1].grade, "A");
  });
});
