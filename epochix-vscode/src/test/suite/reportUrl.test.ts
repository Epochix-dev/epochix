/**
 * The prefilled bug report has to arrive readable.
 *
 * A tester's first report reached GitHub as "%23%23%23 What looks wrong%3F"
 * instead of "### What looks wrong?". The feedback channel for a whole tester
 * round was rendering escape codes, and nothing failed: the button worked, the
 * browser opened, the issue form appeared. Only the text was wrong.
 *
 * The escaping rules differ per surface, and only VS Code's is unusual, so
 * these assertions run in the extension host against the real `vscode.Uri`
 * rather than a stand-in.
 */
import * as assert from "assert";
import * as fs from "fs";
import * as path from "path";

import * as vscode from "vscode";

import { buildUrl } from "../../util/uri";

const ISSUE_URL = "https://github.com/Epochix-dev/epochix/issues/new";

/** Every character class that has bitten this URL, in one string. */
const BODY = [
  "### What looks wrong?",
  "",
  "> accuracy climbs — steadily, not spectacularly",
  "",
  "---",
  "```",
  "epochix      0.5.94",
  "surface      dashboard",
  "metric       val_accuracy",
  "last value   0.98",
  "grade        A",
  "```",
  "",
  "_No run name, file path or log content is included._",
].join("\n");

const PARAMS = { labels: "correctness", title: "Dashboard: ", body: BODY };

/** What the receiving site parses out of a URL — the only thing that matters. */
function paramsAsReceived(url: string): URLSearchParams {
  return new URLSearchParams(url.slice(url.indexOf("?") + 1));
}

suite("Prefilled issue URL", () => {
  test("the URL we build carries the report verbatim", () => {
    const received = paramsAsReceived(buildUrl(ISSUE_URL, PARAMS));

    assert.strictEqual(received.get("body"), BODY);
    assert.strictEqual(received.get("title"), "Dashboard: ");
    // The mangled query cost the labels too, which is how the report lost its
    // triage label as well as its formatting.
    assert.strictEqual(received.get("labels"), "correctness");
  });

  test("opening it as a Uri would corrupt it — which is why we pass a string", () => {
    // VS Code's opener, verbatim: given a Uri it sends
    // `encodeURI(uri.toString(true))`. `toString(true)` writes the query back
    // as raw text and `encodeURI` escapes `%`, so one round of encoding
    // becomes two. Given the original string it sends that untouched.
    const url = buildUrl(ISSUE_URL, PARAMS);
    const asVsCodeWouldSendAUri = encodeURI(
      vscode.Uri.parse(url).toString(true),
    );

    const received = paramsAsReceived(asVsCodeWouldSendAUri);
    assert.notStrictEqual(received.get("body"), BODY);
    assert.ok(
      received.get("body")?.includes("%23%23%23"),
      "expected the double-encoded heading this test exists to prevent",
    );

    // If this ever goes red because the Uri route now round-trips, the cast in
    // openExternalUrl can go. Do not "fix" it by loosening the assertion.
  });

  test("Uri.toString() loses the parameters altogether", () => {
    // The first attempted fix rebuilt the Uri and relied on toString(), which
    // escapes the `&` and `=` separators. GitHub then sees a single nameless
    // parameter: no body, no title, no labels.
    const received = paramsAsReceived(
      vscode.Uri.parse(buildUrl(ISSUE_URL, PARAMS)).toString(),
    );

    assert.strictEqual(received.get("body"), null);
    assert.strictEqual(received.get("labels"), null);
  });

  test("a metric name needing escapes survives the export URL", () => {
    // Same defect, quieter symptom: the export returns a series nobody asked
    // for rather than an error. Spaces and non-ASCII happen to survive the Uri
    // route; `#` and `?` arrive double-encoded and `&` truncates the value.
    for (const metric of ["acc#1", "acc?1", "train&val", "top-1 acc %"]) {
      const url = buildUrl("http://127.0.0.1:7860/api/export/01ABC/gif", {
        metric,
      });
      assert.strictEqual(paramsAsReceived(url).get("metric"), metric);
    }
  });

  test("nothing outside util/uri.ts calls env.openExternal", () => {
    // The assertions above describe the encoding; this one is what actually
    // holds the fix in place. Every earlier attempt failed by calling
    // `env.openExternal(Uri.parse(url))` somewhere new, and each looked
    // perfectly reasonable in isolation. One door out, so there is one place
    // to get it right.
    const root = path.join(
      vscode.extensions.getExtension("epochix.epochix")!.extensionPath,
      "src",
    );

    const offenders: string[] = [];
    const walk = (dir: string): void => {
      for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) {
          walk(full);
        } else if (entry.name.endsWith(".ts")) {
          const rel = path.relative(root, full).replace(/\\/g, "/");
          // The one allowed caller, and the tests — which describe the API
          // rather than call it, and do not ship.
          if (rel === "util/uri.ts" || rel.startsWith("test/")) {
            continue;
          }
          if (/\benv\.openExternal\s*\(/.test(fs.readFileSync(full, "utf8"))) {
            offenders.push(rel);
          }
        }
      }
    };
    walk(root);

    assert.deepStrictEqual(
      offenders,
      [],
      `call openExternalUrl(url) instead — see util/uri.ts: ${offenders.join(", ")}`,
    );
  });
});
