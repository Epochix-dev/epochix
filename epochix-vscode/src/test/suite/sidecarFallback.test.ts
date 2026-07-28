/**
 * What happens when the Python sidecar is not reachable.
 *
 * A cold-start usability test on a fresh machine hit this on BOTH flagship
 * onboarding buttons — "Try a Demo Run" and "Open Log File" — and got a raw
 * "connect ECONNREFUSED 127.0.0.1:7860" with a dead, empty dashboard. The
 * extension ships a complete standalone engine, so that never had to happen.
 *
 * The existing demo test could not have caught it: it forces
 * `useSidecar: "never"`, which is the mode that already worked.
 */
import * as assert from "assert";
import * as path from "path";

import * as vscode from "vscode";

import { DashboardPanel, describeSidecarError } from "../../webview/DashboardPanel";
import type { ServerManager } from "../../sidecar/ServerManager";

const EXT_ID = "epochix.epochix";

/** A sidecar that is registered but answers nothing — a dead server. */
function deadSidecar(): ServerManager {
  return {
    port: 1,
    parseLogFile: () =>
      Promise.reject(new Error("connect ECONNREFUSED 127.0.0.1:1")),
    dispose: () => undefined,
  } as unknown as ServerManager;
}

suite("Sidecar unreachable — the dashboard must still tell the story", () => {
  test("openLog falls back to the standalone engine and renders frames", async () => {
    const ext = vscode.extensions.getExtension(EXT_ID);
    assert.ok(ext, `extension ${EXT_ID} not found`);
    await ext.activate();

    const demo = vscode.Uri.file(
      path.join(ext.extensionPath, "media", "demo.log"),
    );

    DashboardPanel.openLog(ext.extensionUri, demo, deadSidecar(), "en");
    await new Promise((r) => setTimeout(r, 3000)); // reject → degrade → parse

    const panel = DashboardPanel.current;
    assert.ok(panel, "no dashboard panel was created");

    // White-box on purpose: the point is that the panel switched engines
    // rather than sitting dead. TS `private` is compile-time only.
    const inner = panel as unknown as {
      _engine: { snapshot: () => unknown[] } | null;
      _sidecar: unknown;
    };
    assert.ok(
      inner._engine,
      "panel did not degrade to the standalone engine after the sidecar failed",
    );
    assert.strictEqual(
      inner._sidecar,
      null,
      "panel kept pointing at the dead sidecar",
    );
    assert.ok(
      inner._engine.snapshot().length > 0,
      "degraded panel produced no story frames from the demo log",
    );
  });

  test("a watched terminal still gets an engine when a sidecar is running", async () => {
    // TerminalWatcher used to hand its panel the sidecar, but terminal output
    // reaches the dashboard ONLY via feedLines -> StandaloneEngine, and
    // feedLines is a no-op when a sidecar owns the panel. So "Watch Active
    // Terminal" silently showed nothing for everyone who had the Python
    // package installed — the opposite failure to the demo button's.
    const ext = vscode.extensions.getExtension(EXT_ID);
    assert.ok(ext);
    await ext.activate();

    DashboardPanel.current?.dispose();
    const { TerminalWatcher } = await import("../../terminal/TerminalWatcher");
    const watcher = new TerminalWatcher(ext.extensionUri, "en");

    // Drive the private open path the shell-execution listener uses.
    (watcher as unknown as { _openDashboardIfNeeded: () => void })
      ._openDashboardIfNeeded();

    const panel = DashboardPanel.current;
    assert.ok(panel, "watching a terminal opened no dashboard");
    const inner = panel as unknown as { _engine: unknown };
    assert.ok(
      inner._engine,
      "the terminal dashboard has no engine — every chunk fed to it is dropped",
    );
    watcher.dispose();
  });

  test("socket errors are never shown to the user verbatim", () => {
    const shown = describeSidecarError(
      new Error("connect ECONNREFUSED 127.0.0.1:7860"),
    );
    assert.ok(
      !shown.includes("ECONNREFUSED"),
      `a newcomer would be shown: ${shown}`,
    );
    assert.ok(shown.length > 0);
    assert.ok(
      !describeSidecarError(new Error("connect ETIMEDOUT 1.2.3.4:80")).includes(
        "ETIMEDOUT",
      ),
    );
  });
});

suite("Sidecar version skew", () => {
  test("an older sidecar than the extension is detected", async () => {
    const { isOlder } = await import("../../sidecar/ServerManager");
    // The case observed on a real machine: extension 0.5.36, a stale
    // `pip install epochix` on PATH serving 0.5.0, and nothing said so.
    assert.strictEqual(isOlder("0.5.0", "0.5.36"), true);
    assert.strictEqual(isOlder("0.5.36", "0.5.36"), false);
    assert.strictEqual(isOlder("0.5.37", "0.5.36"), false);
    assert.strictEqual(isOlder("0.4.9", "0.5.0"), true);
    assert.strictEqual(isOlder("1.0.0", "0.9.9"), false);
    // 0.5.9 vs 0.5.10 is the classic string-compare trap.
    assert.strictEqual(isOlder("0.5.9", "0.5.10"), true);
    assert.strictEqual(isOlder("0.5.36-beta.1", "0.5.36"), false);
  });
});

suite("Standalone architecture detection", () => {
  test("the bundled demo lights up the network panel without Python", async () => {
    // The demo command's comment always claimed the architecture panel "lights
    // up", but the standalone engine had no architecture support at all — so
    // with no Python installed, or in an untrusted folder, it never did.
    const { parseArchitecture } = await import("../../story/architecture");
    const ext = vscode.extensions.getExtension(EXT_ID);
    assert.ok(ext);
    const fs = await import("fs");
    const lines = fs
      .readFileSync(path.join(ext.extensionPath, "media", "demo.log"), "utf-8")
      .split(/\r?\n/);

    const layers = parseArchitecture(lines);
    assert.ok(layers.length >= 4, `only ${layers.length} layers parsed`);
    assert.ok(
      layers.some((l) => l.params > 0),
      "every layer reported 0 params — the counts were not read",
    );
    assert.ok(
      layers.some((l) => l.visual_type === "conv"),
      "no convolutional layer classified",
    );
  });

  test("a torch print(model) dump reports unknown counts, not zero", async () => {
    const { parseArchitecture } = await import("../../story/architecture");
    const layers = parseArchitecture(
      [
        "Sequential(",
        "  (0): Conv2d(1, 32, kernel_size=(3, 3), stride=(1, 1))",
        "  (1): Linear(in_features=256, out_features=10, bias=True)",
        ")",
      ],
    );
    assert.strictEqual(layers.length, 2);
    // A repr carries no counts; claiming 0 would be false, so it reads empty.
    assert.strictEqual(layers[0].params_str, "");
  });
});


suite("Architecture arrives one line at a time", () => {
  test("a summary fed line-by-line yields every layer, not just the first", async () => {
    // A log is streamed, so the first successful parse sees exactly ONE layer.
    // Latching there reported a single-layer model for an eight-layer network,
    // and the panel silently showed a fraction of the truth.
    const { StandaloneEngine } = await import("../../webview/StandaloneEngine");
    const ext = vscode.extensions.getExtension(EXT_ID);
    assert.ok(ext);
    const fs = await import("fs");
    const lines = fs
      .readFileSync(path.join(ext.extensionPath, "media", "demo.log"), "utf-8")
      .split(/\r?\n/);

    const engine = new StandaloneEngine();
    for (const line of lines) engine.feed(line + "\n");
    engine.flush();

    const arch = engine.architecture();
    assert.ok(
      arch.length >= 6,
      `only ${arch.length} layers survived streaming — the parse latched early`,
    );
    const total = arch.reduce((sum, l) => sum + l.params, 0);
    assert.strictEqual(total, 53002, "parameter total does not match the model");
  });

  test("the demo yields the same metric series the Python side produces", async () => {
    // Diagnostics, metric spread, histograms and the learning-rate chart all
    // read store.metrics, and the extension never sent any — so those panels
    // read "Diagnostics appear once metrics arrive…" forever without Python.
    const { StandaloneEngine } = await import("../../webview/StandaloneEngine");
    const ext = vscode.extensions.getExtension(EXT_ID);
    assert.ok(ext);
    const fs = await import("fs");
    const lines = fs
      .readFileSync(path.join(ext.extensionPath, "media", "demo.log"), "utf-8")
      .split(/\r?\n/);

    const engine = new StandaloneEngine();
    for (const line of lines) engine.feed(line + "\n");
    engine.flush();

    const metrics = engine.metrics();
    const keys = [...new Set(metrics.map((m) => m.canonical_key))].sort();

    // Exactly what `epochix parse` reports for the same file.
    assert.deepStrictEqual(keys, [
      "accuracy",
      "lr",
      "train_loss",
      "val_accuracy",
      "val_loss",
    ]);

    // "Total params: 53,002" must not be charted — the comma made it 53.
    assert.ok(
      !keys.includes("params"),
      "a model-summary total was charted as a metric",
    );

    // Training accuracy must stay distinct from validation accuracy. Aliasing
    // them produced 40 val_accuracy points for a 20-epoch run, half of which
    // were training numbers.
    assert.strictEqual(
      metrics.filter((m) => m.canonical_key === "val_accuracy").length,
      20,
      "val_accuracy absorbed another series",
    );
  });
});
