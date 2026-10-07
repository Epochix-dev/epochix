/**
 * A thresholds file added or edited while a run is open re-grades that run.
 *
 * The panel read `.epochix.yaml` once, when its engine was created, so a file
 * written while a run was on screen applied from the next run only. Now the
 * panel keeps the text it was fed and, when the file changes, reads the run
 * again with the new thresholds; a watcher on every folder the file would be
 * read from tells it when.
 */
import * as assert from "assert";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";

import { gradeConfigFolders, readGradeConfigFile, watchGradeConfig } from "../../gradeConfigFile";
import { parseGradeConfig } from "../../story/gradeConfig";
import { ReplayBuffer, regrade } from "../../webview/replay";

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

const LOG =
  [0.58, 0.66, 0.74, 0.82, 0.9]
    .map((v, i) => `Epoch ${i + 1}/5 train_loss=${(1 / (i + 1)).toFixed(3)} val_accuracy=${v}`)
    .join("\n") + "\n";

function buffered(text: string, ended: boolean, limit?: number): ReplayBuffer {
  const buffer = new ReplayBuffer(limit);
  // Fed in pieces, as a terminal or a file stream delivers it.
  for (let i = 0; i < text.length; i += 37) buffer.add(text.slice(i, i + 37));
  if (ended) buffer.end();
  return buffer;
}

function waitFor(predicate: () => boolean, ms: number): Promise<boolean> {
  return new Promise((resolve) => {
    const start = Date.now();
    const tick = (): void => {
      if (predicate()) return resolve(true);
      if (Date.now() - start > ms) return resolve(false);
      setTimeout(tick, 50);
    };
    tick();
  });
}

suite("A changed thresholds file re-grades the open run", () => {
  test("the same input, read again, is graded with the new thresholds", () => {
    const buffer = buffered(LOG, true);
    const before = regrade(buffer, null, undefined, "en");
    assert.ok(before !== null);
    const frames = before.engine.snapshot();
    assert.strictEqual(frames.length, 5);
    assert.strictEqual(frames[4].grade, "A", "premise: 90% is an A built in");
    assert.strictEqual(before.summary?.finalGrade, "A");

    const strict = parseGradeConfig(STRICT).config;
    const after = regrade(buffer, strict, undefined, "en");
    assert.ok(after !== null);
    const regraded = after.engine.snapshot();
    assert.deepStrictEqual(
      regraded.map((f) => f.primaryMetricValue),
      frames.map((f) => f.primaryMetricValue),
      "the same readings",
    );
    assert.deepStrictEqual([...new Set(regraded.map((f) => f.grade))], ["F"]);
    assert.strictEqual(after.summary?.finalGrade, "F");
  });

  test("a run still in progress is re-read without being finished", () => {
    const result = regrade(buffered(LOG, false), null, undefined, "en");
    assert.ok(result !== null);
    assert.strictEqual(result.summary, null);
    assert.strictEqual(result.engine.snapshot().length, 5);
  });

  test("a run too long to keep is not re-read in part", () => {
    const buffer = buffered(LOG, true, 100);
    assert.strictEqual(buffer.complete, false);
    assert.strictEqual(regrade(buffer, null, undefined, "en"), null);
  });

  test("the folders watched are the ones the file is read from", () => {
    const start = path.join(os.tmpdir(), "a", "b");
    const home = path.join(os.tmpdir(), "home");
    const folders = gradeConfigFolders(start, home);
    assert.strictEqual(folders[0], path.resolve(start));
    assert.strictEqual(folders[1], path.dirname(path.resolve(start)));
    assert.strictEqual(folders[folders.length - 1], path.join(home, ".epochix"));
    assert.deepStrictEqual(gradeConfigFolders(undefined, undefined), []);
  });

  test("the watcher sees a file appear, change and go away", async () => {
    const folder = fs.mkdtempSync(path.join(os.tmpdir(), "epochix-watch-"));
    let calls = 0;
    const watcher = watchGradeConfig(() => calls++, [folder], 50);
    try {
      // Give the watcher a moment to start before the first write.
      await new Promise((r) => setTimeout(r, 500));
      const file = path.join(folder, ".epochix.yaml");
      fs.writeFileSync(file, STRICT, "utf8");
      assert.ok(await waitFor(() => calls >= 1, 8000), "a new file was not noticed");
      assert.ok(readGradeConfigFile(file) !== null);

      const seen = calls;
      fs.writeFileSync(file, STRICT.replace("0.995", "0.9"), "utf8");
      assert.ok(await waitFor(() => calls > seen, 8000), "an edit was not noticed");

      const before = calls;
      fs.unlinkSync(file);
      assert.ok(await waitFor(() => calls > before, 8000), "a deletion was not noticed");

      // A deletion can be reported twice on some platforms; let it settle
      // before checking that an unrelated file is ignored.
      await new Promise((r) => setTimeout(r, 1500));
      const settled = calls;
      fs.writeFileSync(path.join(folder, "other.yaml"), STRICT, "utf8");
      await new Promise((r) => setTimeout(r, 1500));
      assert.strictEqual(calls, settled, "another file is not the thresholds file");
    } finally {
      watcher.dispose();
      fs.rmSync(folder, { recursive: true, force: true });
    }
  });
});
