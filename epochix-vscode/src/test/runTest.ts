/**
 * Integration-test entry point.
 *
 * Downloads a pinned VS Code build, launches it with the extension loaded from
 * the repo root, and runs the Mocha suite in `suite/index` inside that host.
 */
import * as path from "path";

import { runTests } from "@vscode/test-electron";

async function main(): Promise<void> {
  try {
    // The folder containing package.json (extension manifest) — two levels up
    // from out/test/runTest.js.
    const extensionDevelopmentPath = path.resolve(__dirname, "../../");
    const extensionTestsPath = path.resolve(__dirname, "./suite/index");

    await runTests({
      extensionDevelopmentPath,
      extensionTestsPath,
      // Empty workspace, no other extensions — isolate our activation path.
      launchArgs: ["--disable-extensions", "--disable-gpu"],
    });
  } catch (err) {
    console.error("Failed to run integration tests:", err);
    process.exit(1);
  }
}

void main();
