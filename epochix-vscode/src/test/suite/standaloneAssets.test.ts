/**
 * Standalone mode must load the bundle it ships.
 *
 * `buildWebviewHtml` reads `webview-dist/index.html` and rewrites its asset
 * references to `asWebviewUri` values, because a webview document cannot fetch
 * a relative or root-absolute path off disk.
 *
 * What ships in `webview-dist/` is the output of `build:webview`
 * (frontend/vite.webview.config.js), produced by `vscode:prepublish` when
 * `vsce package` runs: one nonce'd `./main.js` and one `./main.css`, because
 * the webview CSP admits exactly one script and a lazy chunk would be blocked.
 *
 * History worth keeping, because these tests once enforced the opposite:
 * 0.7.5 replaced a working `(?:\.\/)?main\.js` rewrite with a pattern that
 * could not match a leading `./`, reasoning that "this build never emits
 * main.js". That was true only of the SERVER bundle (`npm run build`, hashed
 * `/assets/index-*.js`), which CI was copying into webview-dist — and which
 * `vsce package` then overwrites. So every test here validated an artifact that
 * never shipped, passed, and 0.7.5 through 0.7.10 went out with an unrewritten
 * `src="./main.js"`: a blank panel for everyone without the Python sidecar.
 *
 * This is the no-sidecar path: what a user who has not `pip install`ed epochix
 * sees, and what `_degradeToStandalone` falls back to when the server dies.
 */
import * as assert from "assert";
import * as fs from "fs";
import * as path from "path";

import * as vscode from "vscode";

import { buildWebviewHtml } from "../../webview/webview.html";

const EXT_ID = "epochix.epochix";

async function standaloneHtml(): Promise<{ html: string; root: string }> {
  const ext = vscode.extensions.getExtension(EXT_ID);
  assert.ok(ext, `extension ${EXT_ID} not found`);
  await ext.activate();

  const panel = vscode.window.createWebviewPanel(
    "epochix.assetTest",
    "asset test",
    vscode.ViewColumn.One,
    {
      enableScripts: true,
      localResourceRoots: [
        vscode.Uri.joinPath(ext.extensionUri, "webview-dist"),
      ],
    },
  );
  try {
    const html = buildWebviewHtml({
      extensionUri: ext.extensionUri,
      webview: panel.webview,
      sidecarUrl: undefined,
      theme: "dark",
      locale: "en",
    });
    return { html, root: path.join(ext.extensionPath, "webview-dist") };
  } finally {
    panel.dispose();
  }
}

function distRoot(): string {
  const ext = vscode.extensions.getExtension(EXT_ID);
  assert.ok(ext);
  return path.join(ext.extensionPath, "webview-dist");
}

suite("Standalone webview assets", () => {
  test("the bundle under test is the one the release ships", () => {
    // Premise guard. If this fails, webview-dist was filled from the wrong
    // build (the server bundle) and every other test in this suite would be
    // checking an artifact that never reaches a user — which is precisely how
    // a blank panel survived six releases.
    const root = distRoot();
    const index = fs.readFileSync(path.join(root, "index.html"), "utf-8");
    assert.ok(
      /<script type="module"[^>]*src="\.\/main\.js"/.test(index),
      "webview-dist/index.html does not load ./main.js — it was not built with " +
        `\`npm run build:webview\`. Got:\n${index.slice(0, 600)}`,
    );
    assert.ok(fs.existsSync(path.join(root, "main.js")), "no webview-dist/main.js");
    assert.ok(fs.existsSync(path.join(root, "main.css")), "no webview-dist/main.css");
  });

  test("exactly one script is loaded, as the CSP requires", async () => {
    // The CSP is `script-src 'nonce-…'`: one nonce, one module script. A second
    // script tag or a lazily imported chunk is blocked at runtime.
    const { html } = await standaloneHtml();
    const moduleScripts = html.match(/<script type="module"[^>]*>/g) ?? [];
    assert.strictEqual(moduleScripts.length, 1, JSON.stringify(moduleScripts));
    assert.ok(/nonce="[^"]+"/.test(moduleScripts[0]), "the module script has no nonce");
  });

  test("no asset reference survives unrewritten", async () => {
    const { html } = await standaloneHtml();
    const stale = [...html.matchAll(/(?:src|href)="([^"]+)"/g)]
      .map((m) => m[1])
      .filter(
        (u) =>
          !u.startsWith("data:") && !u.startsWith("https://") && u !== "#",
      )
      .filter((u) => !/^(?:vscode-webview-resource|https:\/\/file\+)/.test(u));
    assert.deepStrictEqual(
      stale,
      [],
      `these asset URLs were never rewritten to webview URIs: ${JSON.stringify(stale)}`,
    );
  });

  test("every rewritten asset points at a file that exists", async () => {
    const { html, root } = await standaloneHtml();
    const refs = [...html.matchAll(/(?:src|href)="([^"]+)"/g)]
      .map((m) => m[1])
      .filter((u) => u.includes("webview-dist"));
    assert.ok(refs.length >= 2, `expected script+style refs, got ${refs.length}`);
    for (const ref of refs) {
      const name = decodeURIComponent(
        ref.split("webview-dist")[1].split("?")[0],
      );
      const onDisk = path.join(root, name);
      assert.ok(
        fs.existsSync(onDisk),
        `webview points at ${name}, which is not in webview-dist/`,
      );
    }
  });

  test("the webview is told which extension version rendered it", async () => {
    // Standalone mode has no sidecar, so the dashboard's report button cannot
    // ask `/api/version` and filed "epochix (unavailable)" every time. Issue
    // #35 is one of those reports: a real one, with no version on it.
    const { html } = await standaloneHtml();
    const ext = vscode.extensions.getExtension(EXT_ID);
    assert.ok(ext);
    const version = String(ext.packageJSON.version);
    assert.ok(
      html.includes("__EPOCHIX_EXT_VERSION__"),
      "the webview bridge never sets __EPOCHIX_EXT_VERSION__",
    );
    assert.ok(
      html.includes(JSON.stringify(version)),
      `the bridge does not carry the real version ${version}`,
    );
    assert.ok(
      !html.includes('"unknown"'),
      "the version fell back to 'unknown' — package.json was not readable",
    );
  });

  test("the warning strip ships in the standalone bundle", async () => {
    const { html, root } = await standaloneHtml();
    assert.ok(
      html.includes('id="warning-strip"'),
      "standalone HTML has no warning strip mount point",
    );
    const js = fs.readFileSync(path.join(root, "main.js"), "utf-8");
    assert.ok(
      js.includes("warning-strip"),
      "main.js never touches the warning strip",
    );
  });
});
