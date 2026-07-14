/**
 * Mocha runner executed *inside* the VS Code extension host.
 *
 * The `vscode` module is only importable from here (the host injects it), so
 * every real integration assertion lives in the `*.test.ts` files this loads.
 */
import * as path from "path";

import { glob } from "glob";
import Mocha from "mocha";

export async function run(): Promise<void> {
  const mocha = new Mocha({ ui: "tdd", color: true, timeout: 60_000 });
  const testsRoot = __dirname;

  const files = await glob("**/*.test.js", { cwd: testsRoot });
  for (const f of files) {
    mocha.addFile(path.resolve(testsRoot, f));
  }

  await new Promise<void>((resolve, reject) => {
    mocha.run((failures) => {
      if (failures > 0) {
        reject(new Error(`${failures} test(s) failed.`));
      } else {
        resolve();
      }
    });
  });
}
