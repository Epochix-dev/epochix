/**
 * Standalone mode must load the bundle it ships.
 *
 * `buildWebviewHtml` reads the vendored `webview-dist/index.html` and rewrites
 * its asset references to `asWebviewUri` values, because a webview document
 * cannot fetch a plain relative or root-absolute path off disk. The rewrite
 * looked for `main.js` / `main.css` — names Vite has never emitted here. It
 * emits content-hashed `assets/index-<hash>.js`, so the rewrite matched
 * nothing and the shipped HTML kept `src="/assets/index-<hash>.js"`, which
 * resolves against the webview origin and 404s. Blank panel.
 *
 * This is the no-sidecar path: exactly what a user who has not `pip install`ed
 * epochix sees, and what `_degradeToStandalone` falls back to when the server
 * dies mid-run.
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

suite("Standalone webview assets", () => {
  test("the vendored bundle really is hash-named, not main.js", () => {
    const ext = vscode.extensions.getExtension(EXT_ID);
    assert.ok(ext);
    const root = path.join(ext.extensionPath, "webview-dist");
    const index = fs.readFileSync(path.join(root, "index.html"), "utf-8");
    // Guards the premise: if the build ever does emit main.js this test's
    // reasoning changes, and it should fail loudly rather than pass vacuously.
    assert.ok(
      /src="[^"]*assets\/index-[A-Za-z0-9_-]+\.js"/.test(index),
      `expected a hashed entry script in the built index.html, got:\n${index.slice(0, 600)}`,
    );
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

  test("the warning strip ships in the standalone bundle", async () => {
    const { html, root } = await standaloneHtml();
    assert.ok(
      html.includes('id="warning-strip"'),
      "standalone HTML has no warning strip mount point",
    );
    const entry = fs
      .readdirSync(path.join(root, "assets"))
      .find((f) => /^index-.*\.js$/.test(f));
    assert.ok(entry, "no entry bundle in webview-dist/assets");
    const js = fs.readFileSync(path.join(root, "assets", entry), "utf-8");
    assert.ok(
      js.includes("warning-strip"),
      "the entry bundle never touches the warning strip",
    );
  });
});
