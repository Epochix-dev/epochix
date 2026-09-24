/**
 * The extension's own engine must tell the same truth as the Python one.
 *
 * AGENTS.md: "Parsers exist twice… a fix to one must be ported to the other."
 * The standalone engine — what everyone without the Python package gets — had
 * drifted far behind. Driven through the log shapes that exposed Python bugs
 * in 0.7.7 and 0.7.8, it produced:
 *
 *   * NO STORY AT ALL for a plain `loss` / `val_loss` log, a YOLO loss log, an
 *     XGBoost log, a ROUGE log and a run that went to NaN — six of nine shapes.
 *     Unrecognised metrics defaulted to "classification", which then waited
 *     for a val_accuracy that was never logged.
 *   * "Patterns are starting to click" for a validation accuracy FALLING from
 *     0.79 to 0.60.
 *   * A plateau warning on a steadily FALLING loss, and "Grade improved to F".
 *   * XGBoost graded on its TRAINING loss: the universal parser collapsed
 *     `train-logloss` and `valid-logloss` into one key and kept the first.
 *
 * These drive the real StandaloneEngine end to end. Its run id — and so its
 * narrative variant — is random, so assertions hold for every variant.
 */
import * as assert from "assert";

import { StandaloneEngine } from "../../webview/StandaloneEngine";
import { BoostingParser } from "../../parsers/boosting";
import { makeContext } from "../../parsers/base";
import { _VARIANTS } from "../../story/narrator";
import type { StoryFrameMsg } from "../../webview/messages";

interface Run {
  frames: StoryFrameMsg[];
  engine: StandaloneEngine;
  last: StoryFrameMsg;
  text: string;
}

function drive(lines: string[], opts: { flush?: boolean } = {}): Run {
  const engine = new StandaloneEngine();
  const frames: StoryFrameMsg[] = [];
  for (const line of lines) frames.push(...engine.feed(line + "\n"));
  if (opts.flush !== false) frames.push(...engine.flush());
  assert.ok(frames.length > 0, `no story at all for:\n${lines.slice(0, 3).join("\n")}`);
  return {
    frames,
    engine,
    last: frames[frames.length - 1],
    text: frames.map((f) => f.narrative).join(" \n "),
  };
}

const range = (n: number, f: (e: number) => string): string[] =>
  Array.from({ length: n }, (_, i) => f(i + 1));

const kerasLoss = (vals: number[]): string[] =>
  vals.map((v, i) => `Epoch ${i + 1}/${vals.length} - loss: ${(v * 0.9).toFixed(4)} - val_loss: ${v.toFixed(4)}`);

const GRADE_ORDER = ["F", "D", "C-", "C", "C+", "B-", "B", "B+", "A-", "A", "A+"];
const rank = (g: string): number => GRADE_ORDER.indexOf(g);

suite("Standalone engine — every common log shape tells a story", () => {
  test("a plain loss / val_loss log", () => {
    const r = drive(kerasLoss([0.9, 0.7, 0.55, 0.45, 0.38, 0.33, 0.3, 0.28]));
    assert.strictEqual(r.engine.primaryMetricKey(), "val_loss");
    assert.ok(rank(r.last.grade) >= rank("B"), `a falling loss graded ${r.last.grade}`);
  });

  test("a YOLO log of box_loss / cls_loss, before mAP exists", () => {
    const r = drive(range(10, (e) =>
      `Epoch ${e}/10 box_loss=${(1.8 * 0.87 ** e).toFixed(4)} cls_loss=${(1.2 * 0.85 ** e).toFixed(4)}`));
    assert.strictEqual(r.last.taskType, "detection");
    assert.ok(!/\bmAP\b/.test(r.text), `a loss was narrated as mAP: ${r.last.narrative}`);
  });

  test("an unnamed-but-real metric is narrated by its real name", () => {
    const r = drive(range(8, (e) => `step ${e} score=${(0.5 + 0.04 * e).toFixed(4)}`));
    assert.ok(r.text.includes("score"), r.last.narrative);
  });
});

suite("Standalone engine — boosting logs", () => {
  const xgb = Array.from({ length: 12 }, (_, k) => {
    const i = k * 5;
    return `[${i}]\ttrain-logloss:${(0.68 * 0.94 ** (i / 5)).toFixed(5)}\tvalid-logloss:${(0.7 * 0.95 ** (i / 5) + 0.02).toFixed(5)}`;
  });

  test("XGBoost is graded on VALIDATION log loss, not training", () => {
    const r = drive(xgb);
    assert.strictEqual(r.engine.primaryMetricKey(), "val_log_loss");
    // The last row's validation value, not its training value (0.34428).
    assert.strictEqual(r.last.primaryMetricValue, 0.41816);
  });

  test("a log loss is never narrated as accuracy", () => {
    const r = drive(xgb);
    assert.ok(!/accuracy|\d%/i.test(r.text), `log loss told as accuracy: ${r.last.narrative}`);
  });

  test("the boosting round is the x-axis, so a finished run is not 'just beginning'", () => {
    const r = drive(xgb);
    assert.strictEqual(r.last.epoch, 55);
    assert.ok(!/first examples|has begun/i.test(r.last.narrative), r.last.narrative);
  });

  test("positional eval sets resolve to train then validation", () => {
    const p = new BoostingParser();
    const got = p.parseLine("[3]\tvalidation_0-logloss:0.40000\tvalidation_1-logloss:0.50000", makeContext());
    const byKey = Object.fromEntries(got.map((m) => [m.key, m.value]));
    assert.deepStrictEqual(byKey, { train_logloss: 0.4, val_logloss: 0.5 });
  });

  test("LightGBM's l2 is an error: a falling l2 grades well", () => {
    const r = drive(Array.from({ length: 12 }, (_, k) => `[${k + 1}]\tvalid_0's l2: ${(30000 * 0.85 ** k).toFixed(1)}`));
    assert.ok(rank(r.last.grade) >= rank("B"), `falling l2 graded ${r.last.grade}`);
  });

  test("CatBoost's derived `best` column is not a metric, and no row is read twice", () => {
    const r = drive(Array.from({ length: 12 }, (_, k) =>
      `${k}:\tlearn: ${(0.68 * 0.93 ** k).toFixed(7)}\ttest: ${(0.69 * 0.95 ** k).toFixed(7)}\tbest: ${(0.69 * 0.95 ** k).toFixed(7)} (${k})`));
    const keys = new Set(r.engine.metrics().map((m) => m.canonical_key));
    assert.deepStrictEqual([...keys].sort(), ["train_loss", "val_loss"]);
  });
});

suite("Standalone engine — metric direction and prose", () => {
  test("a rising ROUGE is not graded as a decline, nor called perplexity", () => {
    const r = drive(range(10, (e) =>
      `Epoch ${e}/10 train_loss=${(4.2 * 0.88 ** e).toFixed(4)} rouge=${(0.2 + 0.03 * e).toFixed(4)}`));
    assert.notStrictEqual(r.last.grade, "F");
    assert.ok(!/perplexity|past its best|slipped/i.test(r.text), r.last.narrative);
  });

  test("Dice is not narrated as IoU", () => {
    const r = drive(range(10, (e) =>
      `Epoch ${e}/10 loss=${(1.5 * 0.86 ** e).toFixed(4)} val_Dice=${Math.min(0.93, 0.35 + 0.06 * e).toFixed(4)}`));
    assert.ok(!/\bIoU\b/.test(r.text), r.last.narrative);
  });

  test("a rising R² is never described as an error dropping", () => {
    const r = drive(range(10, (e) =>
      `Epoch ${e}/10 train_loss=${(2 * 0.8 ** e).toFixed(4)} val_r2=${(0.3 + 0.06 * e).toFixed(4)}`));
    assert.ok(!/\berror\b/i.test(r.text), r.last.narrative);
  });

  test("FID: an improving and a worsening run do not share a grade", () => {
    const run = (vals: number[]): Run =>
      drive(vals.map((v, i) => `Epoch ${i + 1}/${vals.length} g_loss=1.0 fid=${v}`));
    const up = run([120, 90, 70, 55, 45, 38, 33, 30]);
    const down = run([30, 33, 38, 45, 55, 70, 90, 120]);
    assert.ok(rank(up.last.grade) > rank(down.last.grade),
      `improving FID ${up.last.grade}, worsening FID ${down.last.grade}`);
  });
});

suite("Standalone engine — runs that are not progressing", () => {
  test("a FALLING validation accuracy is reported as past its peak, not progress", () => {
    const r = drive(range(25, (e) =>
      `Epoch ${e}/25 - loss: ${Math.max(0.05, 2.0 * 0.86 ** e).toFixed(4)} - val_accuracy: ${Math.max(0.55, 0.8 - 0.008 * e).toFixed(4)}`));
    assert.ok(!/starting to click|diligent|progress/i.test(r.last.narrative), r.last.narrative);
    assert.ok(/peak|best|slipped/i.test(r.last.narrative), r.last.narrative);
  });

  test("a flat run is reported as stalled, with advice", () => {
    const r = drive(range(8, (e) =>
      `Epoch ${e}/8 train_loss=2.3010 val_accuracy=${(0.101 + 0.0005 * e).toFixed(4)}`));
    assert.ok(/barely moved|essentially where it started|no meaningful progress/i.test(r.last.narrative),
      r.last.narrative);
  });

  test("no past-peak or stalled variant makes a false claim", () => {
    for (const v of _VARIANTS.PAST_PEAK) {
      assert.ok(!/below the best/i.test(v), `"below" is false for a loss: ${v}`);
      assert.ok(!/overfitting/i.test(v), `past-peak cannot know the cause: ${v}`);
    }
    for (const v of _VARIANTS.STALLED) {
      assert.ok(/learning rate|setup problem/i.test(v), `stalled variant gives no advice: ${v}`);
    }
  });
});

suite("Standalone engine — divergence", () => {
  const nanLog = [
    "Epoch 1/6 - loss: 0.9000 - val_loss: 0.9500",
    "Epoch 2/6 - loss: 0.7000 - val_loss: 0.7600",
    "Epoch 3/6 - loss: 0.5000 - val_loss: 0.5900",
    "Epoch 4/6 - loss: nan - val_loss: nan",
    "Epoch 5/6 - loss: nan - val_loss: nan",
  ];

  test("a loss that becomes NaN ends the story as F, with a warning", () => {
    const r = drive(nanLog);
    assert.strictEqual(r.last.grade, "F");
    assert.ok(r.engine.warnings().some((w) => w.kind === "divergence"));
    assert.ok(r.last.narrative.includes("0.5900"), `no real last value: ${r.last.narrative}`);
  });

  test("it is reported WITHOUT an end of stream — a live run never ends", () => {
    // Enough lines to get past format sniffing (it holds up to six while it
    // decides), and never flush(): a live terminal run has no end to wait for.
    const live = [...nanLog, "Epoch 6/9 - loss: nan - val_loss: nan", "Epoch 7/9 - loss: nan - val_loss: nan"];
    const r = drive(live, { flush: false });
    assert.strictEqual(r.last.grade, "F", "divergence waited for flush()");
  });

  test("no frame is dated past the last real reading", () => {
    const r = drive(nanLog);
    const epochs = r.frames.map((f) => f.epoch).filter((e): e is number => e !== null);
    assert.ok(Math.max(...epochs) <= 3, `invented a reading after epoch 3: ${JSON.stringify(epochs)}`);
  });

  test("every divergence variant quotes the last real value", () => {
    for (const v of _VARIANTS.DIVERGED) assert.ok(v.includes("{value}"), v);
  });

  test("prose containing inf / nan is not mistaken for divergence", () => {
    const r = drive([
      "Namespace(lr=0.001, infer=True, nan_policy='omit')",
      "Loaded 512 inference batches; info: starting run",
      ...kerasLoss([0.9, 0.7, 0.55, 0.45, 0.38]),
    ]);
    assert.notStrictEqual(r.last.grade, "F");
    assert.ok(!r.engine.warnings().some((w) => w.kind === "divergence"));
  });

  test("a gradually exploding loss is warned about", () => {
    const r = drive(range(8, (e) => {
      const v = 1.2 * 2.6 ** e;
      return `Epoch ${e}/8 - loss: ${v.toFixed(4)} - val_loss: ${(v * 1.15).toFixed(4)}`;
    }));
    assert.ok(r.engine.warnings().some((w) => w.kind === "divergence"));
  });
});

suite("Standalone engine — warnings and milestones do not lie", () => {
  test("a steadily FALLING loss is not a plateau", () => {
    const r = drive(kerasLoss([0.9, 0.7, 0.55, 0.45, 0.38, 0.33, 0.3, 0.28, 0.26, 0.25]));
    assert.ok(!r.engine.warnings().some((w) => w.kind === "plateau"),
      JSON.stringify(r.engine.warnings()));
  });

  test("validation loss rising while training loss falls is overfitting", () => {
    const r = drive(range(10, (e) =>
      `Epoch ${e}/10 - loss: ${(2 * 0.8 ** e).toFixed(4)} - val_loss: ${(0.5 + 0.1 * e).toFixed(4)}`));
    assert.ok(r.engine.warnings().some((w) => w.kind === "overfit"));
  });

  test("a falling grade is never announced as an improvement", () => {
    const r = drive(range(25, (e) =>
      `Epoch ${e}/25 - loss: ${Math.max(0.05, 2.0 * 0.86 ** e).toFixed(4)} - val_accuracy: ${(e <= 8 ? 0.6 + 0.045 * e : 0.96 - 0.03 * (e - 8)).toFixed(4)}`));
    const grades = r.frames.map((f) => f.grade);
    for (const m of r.engine.milestones().filter((x) => x.kind === "grade_transition")) {
      const to = m.message.split(" to ")[1];
      const idx = grades.lastIndexOf(to as StoryFrameMsg["grade"]);
      assert.ok(idx > 0, `milestone for a grade no frame had: ${m.message}`);
    }
    assert.ok(
      r.engine.milestones().some((m) => /dropped/.test(m.message)),
      `a run that fell from A to worse never said so: ${JSON.stringify(r.engine.milestones())}`,
    );
  });

  test("a healthy run trips no warning at all", () => {
    const r = drive(range(15, (e) =>
      `Epoch ${e}/15 - loss: ${(2.3 * 0.8 ** e).toFixed(4)} - val_loss: ${(2.3 * 0.82 ** e + 0.05).toFixed(4)} - val_accuracy: ${Math.min(0.97, 0.35 + 0.045 * e).toFixed(4)}`));
    assert.deepStrictEqual(r.engine.warnings(), []);
  });
});
