/**
 * A watched command that printed something Epochix did not tell is said to
 * have been seen — and a command that is not training is not.
 *
 * Both issues ever opened by people outside the project came from an empty
 * dashboard; a command whose output the terminal feed never recognised
 * produced no panel and no message, so nobody knew their run had been seen.
 *
 * The rule is held to recordings (tests/fixtures/terminal): ordinary commands,
 * recorded from a neutral folder, must say nothing; a Stable-Baselines3 run,
 * a layout nothing reads, must say it was seen and not read. And to the whole
 * corpus: no training log may end silent, with neither a dashboard nor a word.
 */
import * as assert from "assert";
import * as fs from "fs";
import * as path from "path";

import * as vscode from "vscode";

import { CommandReading, LABELLED_MIN_VALUES, labelledNumbers, type Verdict } from "../../terminal/CommandReading";
import { noticeText } from "../../terminal/noticeText";
import { StandaloneEngine } from "../../webview/StandaloneEngine";

const EXT_ID = "epochix.epochix";
const LOCALES = ["en", "fa", "fr"] as const;
const PERSIAN = /[؀-ۿ]/;

function repoRoot(): string {
  const ext = vscode.extensions.getExtension(EXT_ID);
  assert.ok(ext, `extension ${EXT_ID} not found`);
  return path.resolve(ext.extensionPath, "..");
}

const terminalLog = (name: string): string =>
  path.join(repoRoot(), "tests", "fixtures", "terminal", name);

/** Terminals do not respect line endings: chunks of n characters. */
function chunked(text: string, n: number): string[] {
  const out: string[] = [];
  for (let i = 0; i < text.length; i += n) out.push(text.slice(i, i + n));
  return out;
}

/** A command's whole output through a reading, as the watcher drives one. */
function read(text: string, n = 997): { reading: CommandReading; verdict: Verdict | null } {
  const reading = new CommandReading();
  for (const chunk of chunked(text, n)) reading.push(chunk);
  reading.end();
  return { reading, verdict: reading.verdict(new StandaloneEngine()) };
}

/** The ordinary commands the README lists as recordings. */
function ordinaryRecordings(): string[] {
  const readme = fs.readFileSync(terminalLog("README.md"), "utf-8");
  const names = [...readme.matchAll(/^\| `([\w.-]{1,80}\.log)` \|/gm)].map((m) => m[1]);
  return names.filter((n) => n !== "sb3_ppo_real.log");
}

interface Expectation {
  path: string;
  frames: number;
}

function corpus(): Record<string, Expectation> {
  const file = path.join(repoRoot(), "tests", "fixtures", "corpus_truth.json");
  return JSON.parse(fs.readFileSync(file, "utf-8")) as Record<string, Expectation>;
}

/** Every name the verdict quotes, so the numbers left can be checked. */
function names(verdict: Verdict): string[] {
  if (verdict.kind === "unopened") return [verdict.metric];
  return [...verdict.readings, ...verdict.labelled].map(([name]) => name);
}

/** The counts the verdict may quote — each one counted from the output. */
function counts(verdict: Verdict): Set<string> {
  const out = new Set([String(verdict.lines)]);
  if (verdict.sampled !== null) out.add(String(verdict.sampled));
  if (verdict.kind === "unopened") out.add(String(verdict.count));
  else for (const [, n] of [...verdict.readings, ...verdict.labelled]) out.add(String(n));
  return out;
}

/** Every rendering of a verdict: numbers only from the output, nothing of the
 *  output but the names it quotes, and the language it was asked for. */
function assertRendered(verdict: Verdict, text: string, where: string): void {
  const logLines = text.split(/\r?\n/).map((l) => l.trim()).filter((l) => l.length > 12);
  for (const locale of LOCALES) {
    const said = noticeText(verdict, locale);
    const all = [said.status, ...said.sentences].join("\n");
    assert.ok(!/\{[a-z_]+\}/.test(all), `${where}/${locale}: a placeholder was left: ${all}`);
    if (locale === "fa") assert.ok(PERSIAN.test(all), `${where}: not in Persian`);
    if (locale !== "en") {
      assert.notStrictEqual(all, [noticeText(verdict, "en").status, ...noticeText(verdict, "en").sentences].join("\n"));
    }
    let numbersOnly = all;
    for (const name of names(verdict)) numbersOnly = numbersOnly.split(name).join(" ");
    for (const n of numbersOnly.match(/\d+/g) ?? []) {
      assert.ok(counts(verdict).has(n), `${where}/${locale}: ${n} is not counted from the output: ${all}`);
    }
    for (const line of logLines) {
      assert.ok(!all.includes(line), `${where}/${locale}: a line of the output was repeated: ${line}`);
    }
    assert.ok(!/[A-Za-z]:\\|\/tmp\//.test(all), `${where}/${locale}: a path was quoted`);
  }
}

suite("A watched command that was not told", () => {
  test("the ordinary commands are recorded and say nothing", () => {
    const logs = ordinaryRecordings();
    // A guard: a renamed folder must not leave this passing on nothing.
    assert.ok(logs.length >= 8, `only ${logs.length} ordinary recordings found`);
    const withGarbage = [...logs.map(terminalLog), path.join(repoRoot(), "tests", "fixtures", "logs", "garbage.log")];
    for (const file of withGarbage) {
      const text = fs.readFileSync(file, "utf-8");
      assert.ok(text.trim().length > 0, `${file} is empty`);
      for (const n of [1, 64, 4096]) {
        const { verdict } = read(text, n);
        assert.strictEqual(verdict, null, `${path.basename(file)} (chunks of ${n}): ${JSON.stringify(verdict)}`);
      }
    }
  });

  test("no ordinary command comes near the threshold", () => {
    for (const name of ordinaryRecordings()) {
      const lines = fs.readFileSync(terminalLog(name), "utf-8").split("\n");
      for (const [label, n] of labelledNumbers(lines)) {
        assert.ok(n < LABELLED_MIN_VALUES, `${name}: ${label} beside ${n} different values`);
      }
    }
  });

  test("a Stable-Baselines3 run is seen and not read", () => {
    const text = fs.readFileSync(terminalLog("sb3_ppo_real.log"), "utf-8");
    const { reading, verdict } = read(text);
    assert.ok(verdict !== null && verdict.kind === "unread", JSON.stringify(verdict));
    assert.strictEqual(reading.opened, false, "the premise: the dashboard never opened for it");
    assert.strictEqual(verdict.opened, false);
    assert.deepStrictEqual(verdict.readings, [], "a reader took something from the table");
    assert.strictEqual(verdict.lines, text.split("\n").length - (text.endsWith("\n") ? 1 : 0));
    assert.strictEqual(verdict.sampled, null);

    // The values beside `loss`, counted here without the scan.
    const losses = new Set(
      [...text.matchAll(/^\|\s+loss\s+\|\s+(\S+)\s+\|/gm)].map((m) => String(parseFloat(m[1]))),
    );
    assert.ok(losses.size >= LABELLED_MIN_VALUES);
    assert.deepStrictEqual(verdict.labelled.find(([name]) => name === "loss"), ["loss", losses.size]);

    const said = noticeText(verdict, "en");
    assert.strictEqual(said.canOpen, false);
    assert.ok(said.sentences.some((s) => s.includes(`${verdict.lines} lines`)), said.sentences.join(" "));
    assert.ok(said.sentences.some((s) => s.includes("None of its readers takes this layout")));
    assert.ok(said.sentences.some((s) => s.includes("train_loss=<value>")), "no fix was offered");
    assertRendered(verdict, text, "sb3_ppo_real.log");
  });

  test("no training log in the corpus ends silent", () => {
    const truth = corpus();
    assert.ok(Object.keys(truth).length >= 50, "the corpus was not found");
    const unopened: string[] = [];
    for (const [name, expected] of Object.entries(truth)) {
      const text = fs.readFileSync(path.join(repoRoot(), expected.path), "utf-8");
      const { reading, verdict } = read(text);
      if (expected.frames === 0) {
        assert.strictEqual(verdict, null, `${name} tells nothing, and was spoken of`);
        continue;
      }
      if (reading.opened) {
        // The dashboard opened and tells it: nothing to add.
        assert.strictEqual(verdict, null, `${name}: ${JSON.stringify(verdict)}`);
        continue;
      }
      assert.ok(verdict !== null && verdict.kind === "unopened", `${name} ends silent: ${JSON.stringify(verdict)}`);
      assert.ok(verdict.count > 0 && verdict.complete, name);
      assert.ok(noticeText(verdict, "en").canOpen, name);
      assertRendered(verdict, text, name);
      unopened.push(name);
    }
    // The runs the terminal feed does not recognise and the engine tells.
    // A change to either shows up here.
    assert.deepStrictEqual(unopened.sort(), [
      "catboost_real_classifier.log",
      "catboost_real_flat_auc.log",
      "gridsearch_cv.log",
      "gridsearch_real.log",
      "gridsearch_real_multimetric.log",
      "gridsearch_real_train_score.log",
    ]);
  });

  test("a story the engine tells of a name it does not know is not offered", () => {
    // The premise, measured: git log is told as frames of `Date`, a uvicorn log
    // as frames of `INFO`. Neither is a run.
    for (const name of ["git_log.log", "uvicorn_server.log"]) {
      const engine = new StandaloneEngine();
      engine.feed(fs.readFileSync(terminalLog(name), "utf-8"));
      engine.flush();
      assert.ok(engine.snapshot().length > 0, `${name}: the premise no longer holds`);
      assert.strictEqual(read(fs.readFileSync(terminalLog(name), "utf-8")).verdict, null, name);
    }
  });

  test("a dashboard that opened and has nothing to show says why", () => {
    // Recognised (an "epoch … loss" line), and nothing a story can be told by:
    // only a learning rate, whose direction says nothing of progress.
    let text = "Training epoch schedule; loss is printed at the end\n";
    for (let e = 1; e <= 6; e++) text += `epoch ${e} lr=${(0.1 / e).toFixed(4)}\n`;
    const { reading, verdict } = read(text, 40);
    assert.strictEqual(reading.opened, true, "the premise: the feed recognised it");
    assert.ok(verdict !== null && verdict.kind === "unread", JSON.stringify(verdict));
    assert.strictEqual(verdict.opened, true);
    assert.deepStrictEqual(verdict.readings, [["lr", 6]]);
    const said = noticeText(verdict, "en");
    assert.ok(said.sentences[0].startsWith("The dashboard opened"), said.sentences[0]);
    assert.ok(said.sentences.some((s) => s.includes("None of these is a score or a loss")));
    assertRendered(verdict, text, "lr only");
  });

  test("output beyond the capture is read from its start, and said so", () => {
    const text = fs.readFileSync(terminalLog("sb3_ppo_real.log"), "utf-8");
    const big = text.repeat(Math.ceil((4 * 1024 * 1024) / text.length) + 1);
    const { verdict } = read(big, 65536);
    assert.ok(verdict !== null && verdict.kind === "unread");
    assert.ok(verdict.sampled !== null && verdict.sampled < verdict.lines, JSON.stringify(verdict.sampled));
    assert.ok(noticeText(verdict, "en").sentences.some((s) => s.includes(`first ${verdict.sampled} lines`)));
  });
});
