/**
 * What the published package leaves out.
 *
 * `.vscodeignore` excluded CHANGELOG.md — the file the Marketplace and Open
 * VSX show on the extension's "Changelog" tab — and did not exclude
 * `eslint.config.mjs`, which shipped to every user. Found by listing a built
 * .vsix: 17 files, the lint config among them, the changelog not.
 *
 * This reads the ignore file rather than building a package, which the test
 * host cannot do; RELEASING's pre-tag step still opens the real .vsix.
 */
import * as assert from "assert";
import * as fs from "fs";
import * as path from "path";

const ROOT = path.resolve(__dirname, "../../..");

function ignored(): string[] {
  return fs
    .readFileSync(path.join(ROOT, ".vscodeignore"), "utf8")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0 && !line.startsWith("#"));
}

suite("The published package", () => {
  test("ships its changelog", () => {
    assert.ok(fs.existsSync(path.join(ROOT, "CHANGELOG.md")), "the changelog is gone");
    const patterns = ignored().map((p) => p.toLowerCase());
    assert.ok(!patterns.includes("changelog.md"), "CHANGELOG.md is excluded from the package");
    assert.ok(!patterns.includes("*.md") && !patterns.includes("**/*.md"), "all markdown is excluded");
  });

  test("does not ship its lint configuration", () => {
    assert.ok(fs.existsSync(path.join(ROOT, "eslint.config.mjs")), "premise: the file exists");
    assert.ok(ignored().includes("eslint.config.mjs"), "eslint.config.mjs would be packaged");
  });

  test("still ships what it runs", () => {
    const patterns = ignored();
    for (const needed of ["dist/**", "webview-dist/**", "media/**", "package.json", "README.md"]) {
      assert.ok(!patterns.includes(needed), `${needed} is excluded`);
    }
  });
});
