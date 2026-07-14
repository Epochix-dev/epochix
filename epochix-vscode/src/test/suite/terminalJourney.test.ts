/**
 * The terminal → dashboard journey, driven end to end.
 *
 * Terminal output arrives as arbitrary chunks (split mid-line, ANSI-coloured,
 * preceded by preamble). This drives that stream through the real TerminalFeed
 * and the real StandaloneEngine — the same path a training run takes — and
 * asserts the story frames come out whole.
 *
 * The bugs this pins down, all of which shipped:
 *  - Output buffered BEFORE detection fired was never fed, so the epochs that
 *    triggered detection never reached the dashboard.
 *  - Detection was re-tested per chunk against a rolling 8 KB tail, so a long
 *    non-metric blob mid-run could stop the feed for the rest of the run.
 */
import * as assert from "assert";

import { TerminalFeed } from "../../terminal/TerminalFeed";
import { isTraining } from "../../terminal/TrainingDetector";
import { StandaloneEngine } from "../../webview/StandaloneEngine";

/** Split text into chunks of n chars — terminals do not respect line endings. */
function chunked(text: string, n: number): string[] {
  const out: string[] = [];
  for (let i = 0; i < text.length; i += n) out.push(text.slice(i, i + n));
  return out;
}

function kerasLog(epochs: number): string {
  let s = "";
  for (let e = 1; e <= epochs; e++) {
    const loss = (2.0 - e * 0.15).toFixed(3);
    const acc = (0.40 + e * 0.05).toFixed(3);
    s += `Epoch ${e}/${epochs}\n`;
    s += `100/100 - 2s - loss: ${loss} - val_accuracy: ${acc}\n`;
  }
  return s;
}

/**
 * Drive chunks through the feed into the engine, returning every frame.
 * Ends with flush(), which is what DashboardPanel does when the watched
 * command finishes.
 */
function run(chunks: string[]): ReturnType<StandaloneEngine["feed"]> {
  const feed = new TerminalFeed();
  const engine = new StandaloneEngine();
  const frames: ReturnType<StandaloneEngine["feed"]> = [];
  for (const chunk of chunks) {
    const feedable = feed.push(chunk);
    if (feedable !== null) frames.push(...engine.feed(feedable));
  }
  frames.push(...engine.flush());
  return frames;
}

suite("Terminal → dashboard journey", () => {
  test("the first epoch survives detection", () => {
    // Detection can only fire once it has SEEN an epoch line, so epoch 1 is
    // always already in the buffer when it trips. It must still be delivered.
    const frames = run(chunked(kerasLog(5), 40));

    assert.ok(frames.length > 0, "no story frames reached the dashboard at all");
    const epochs = frames.map((f) => f.epoch);
    assert.ok(
      epochs.includes(1),
      `epoch 1 was dropped by the pre-detection buffer: got ${JSON.stringify(epochs)}`,
    );
    assert.strictEqual(frames[frames.length - 1].epoch, 5, "the run did not finish");
  });

  test("output before the training starts does not break it", () => {
    const preamble =
      "Collecting torch\nInstalling dependencies...\nLoading dataset: 60000 images\n";
    const frames = run(chunked(preamble + kerasLog(4), 33));

    const epochs = frames.map((f) => f.epoch);
    assert.ok(epochs.includes(1), `epoch 1 missing: ${JSON.stringify(epochs)}`);
    assert.strictEqual(frames[frames.length - 1].epoch, 4);
  });

  test("a long non-metric blob mid-run does not stop the feed", () => {
    // A >8KB burst of non-training output used to push the last "Epoch N/M" out
    // of the rolling window, flipping isTraining() false and silently killing
    // the feed for the remainder of the run.
    const noise = "warning: some very chatty library says something\n".repeat(400);
    const log = kerasLog(3) + noise;

    const feed = new TerminalFeed();
    const engine = new StandaloneEngine();
    const frames: ReturnType<StandaloneEngine["feed"]> = [];

    for (const chunk of chunked(log, 512)) {
      const f = feed.push(chunk);
      if (f !== null) frames.push(...engine.feed(f));
    }
    assert.ok(feed.detected, "detection did not latch");

    // Training resumes after the noise — it must still be delivered.
    const tail = "Epoch 4/4\n100/100 - 2s - loss: 0.410 - val_accuracy: 0.910\n";
    const feedable = feed.push(tail);
    assert.notStrictEqual(feedable, null, "the feed went dead after the noise blob");
    frames.push(...engine.feed(feedable as string));

    assert.strictEqual(
      frames[frames.length - 1].epoch,
      4,
      "the epoch after the noise never reached the dashboard",
    );
  });

  test("ANSI colour codes are stripped before parsing", () => {
    const coloured = "[32mEpoch 1/2[0m\n100/100 - 2s - loss: 1.2 - val_accuracy: 0.55\n";
    const feed = new TerminalFeed();
    const feedable = feed.push(coloured);
    assert.notStrictEqual(feedable, null, "ANSI-coloured training was not detected");
    assert.ok(!feedable!.includes("["), "ANSI escapes reached the parser");
  });

  test("a log with 3 metrics per line still produces frames", () => {
    // Task detection used to fire on `_allMetrics.length === 10` exactly. A log
    // emitting 3 metrics per line counts 3, 6, 9, 12 — it never equals 10, so
    // the task was never detected and not one frame was ever built.
    let log = "";
    for (let e = 1; e <= 6; e++) {
      log += `epoch=${e} train_loss=${(2.0 - e * 0.2).toFixed(3)} val_loss=${(2.2 - e * 0.2).toFixed(3)} val_accuracy=${(0.4 + e * 0.07).toFixed(3)}\n`;
    }
    const frames = run(chunked(log, 30));

    assert.ok(frames.length > 0, "a 3-metric-per-line log produced no frames at all");
    assert.strictEqual(frames[frames.length - 1].epoch, 6);
  });

  test("the universal fallback reads a bare 'Epoch N/M' header", () => {
    // The TS universal parser only understood `epoch=N`, so any log it handled
    // showed "Epoch —" and a dead progress bar (Python got this in 0.5.8).
    const log =
      "Epoch 1/4: train_loss=1.900 val_accuracy=0.510\n" +
      "Epoch 2/4: train_loss=1.500 val_accuracy=0.640\n" +
      "Epoch 3/4: train_loss=1.200 val_accuracy=0.710\n" +
      "Epoch 4/4: train_loss=1.000 val_accuracy=0.780\n";
    const frames = run(chunked(log, 24));

    assert.ok(frames.length > 0, "no frames from a bare-header log");
    const epochs = frames.map((f) => f.epoch);
    assert.deepStrictEqual(
      epochs,
      [1, 2, 3, 4],
      `epochs were dropped or misnumbered: ${JSON.stringify(epochs)}`,
    );
    assert.ok(
      frames[frames.length - 1].progress > 0,
      "totalEpochs was not picked up, so the progress bar never moves",
    );
  });

  test("a plain key=value training log opens the dashboard", () => {
    // sniff() scored `soft * 0.15`, and 3 * 0.15 === 0.4499999999999999 in
    // IEEE — a hair under the 0.45 threshold. A log carrying exactly three soft
    // signals (loss=, accuracy=, val_loss) therefore never opened the dashboard;
    // it silently took four.
    const kv = "epoch=1 train_loss=1.800 val_loss=2.000 val_accuracy=0.470\n";
    assert.ok(isTraining(kv), "an ordinary key=value training log was not recognised");
  });

  test("a live run draws frames before the command ends", () => {
    // Output must reach the dashboard DURING training, not only at flush().
    const feed = new TerminalFeed();
    const engine = new StandaloneEngine();
    const frames: ReturnType<StandaloneEngine["feed"]> = [];

    let log = "";
    for (let e = 1; e <= 10; e++) {
      log += `epoch=${e} train_loss=${(2.0 - e * 0.1).toFixed(3)} val_loss=${(2.2 - e * 0.1).toFixed(3)} val_accuracy=${(0.4 + e * 0.04).toFixed(3)}\n`;
    }
    for (const chunk of chunked(log, 40)) {
      const feedable = feed.push(chunk);
      if (feedable !== null) frames.push(...engine.feed(feedable));
    }

    // No flush() — this is mid-run.
    assert.ok(frames.length > 0, "a live run drew nothing until it finished");
    assert.ok(frames.map((f) => f.epoch).includes(1), "the first epoch was lost");
  });

  test("nothing is fed for output that is not training", () => {
    const feed = new TerminalFeed();
    assert.strictEqual(feed.push("$ ls -la\n"), null);
    assert.strictEqual(feed.push("total 48\ndrwxr-xr-x  7 user staff  224 Jul 14 10:00 .\n"), null);
    assert.strictEqual(feed.detected, false);
  });
});
