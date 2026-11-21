/**
 * The sidecar is the extension's own server, and the user's shell must not
 * lock the extension out of it.
 *
 * It was started with the extension host's whole environment. An
 * `EPOCHIX_AUTH_TOKEN` exported for a remote `epochix serve` therefore reached
 * it too, and nothing in the extension sends a token: saving a run got 401, and
 * the panel's page — an iframe on the sidecar, which sends no header — could
 * not read one back. The sidecar binds loopback only and is reached only by the
 * extension and its own pages, so it is started with the settings for serving
 * beyond this machine (`EPOCHIX_AUTH_TOKEN`, `EPOCHIX_CORS_ORIGINS`) emptied.
 *
 * This drives the real thing: the repository's own `epochix`, started through
 * `ServerManager.maybeStart`, as the extension starts it.
 */
import * as assert from "assert";
import * as fs from "fs";
import * as http from "http";
import * as os from "os";
import * as path from "path";

import type * as vscode from "vscode";

import { ServerManager, sidecarEnv } from "../../sidecar/ServerManager";

/** The repository's virtualenv `epochix` (`uv sync` makes it; CI does). */
function repoEpochix(): string {
  const root = path.resolve(__dirname, "../../../..");
  const exe =
    process.platform === "win32"
      ? path.join(root, ".venv", "Scripts", "epochix.exe")
      : path.join(root, ".venv", "bin", "epochix");
  // Not a skip: a suite that skips this passes having started nothing.
  assert.ok(
    fs.existsSync(exe),
    `no epochix at ${exe} — run \`uv sync --extra dev\` in the repository first`,
  );
  return exe;
}

function settings(values: Record<string, unknown>): vscode.WorkspaceConfiguration {
  return {
    get: <T>(key: string, fallback?: T): T => (key in values ? (values[key] as T) : (fallback as T)),
  } as unknown as vscode.WorkspaceConfiguration;
}

function get(port: number, urlPath: string): Promise<{ status: number; body: string }> {
  return new Promise((resolve, reject) => {
    const req = http.get(`http://127.0.0.1:${port}${urlPath}`, (res) => {
      let body = "";
      res.on("data", (chunk: Buffer) => { body += chunk.toString(); });
      res.on("end", () => resolve({ status: res.statusCode ?? 0, body }));
    });
    req.on("error", reject);
  });
}

suite("The sidecar and the user's EPOCHIX_AUTH_TOKEN", () => {
  const saved: Record<string, string | undefined> = {};
  const vars = ["EPOCHIX_AUTH_TOKEN", "EPOCHIX_CORS_ORIGINS", "EPOCHIX_DB"];
  let sidecar: ServerManager | null = null;
  let dir = "";

  setup(() => {
    for (const v of vars) saved[v] = process.env[v];
    dir = fs.mkdtempSync(path.join(os.tmpdir(), "epochix-sidecar-env-"));
  });

  teardown(() => {
    sidecar?.dispose();
    sidecar = null;
    for (const v of vars) {
      if (saved[v] === undefined) delete process.env[v];
      else process.env[v] = saved[v];
    }
  });

  test("a token in the shell does not lock the extension out of its own server", async function () {
    this.timeout(60_000);
    process.env.EPOCHIX_AUTH_TOKEN = "exported-for-a-remote-server";
    process.env.EPOCHIX_CORS_ORIGINS = "https://story.example.com";
    process.env.EPOCHIX_DB = path.join(dir, "runs.db");

    sidecar = await ServerManager.maybeStart(
      settings({ useSidecar: "always", sidecarPath: repoEpochix() }),
    );
    assert.ok(sidecar, "the sidecar did not start");

    // What the extension writes: a run and its measurements.
    const runId = await sidecar.createRun("sidecar-env", "classification");
    await sidecar.pushEvent(runId, {
      seq: 0, epoch: 1, canonical_key: "val_accuracy", raw_key: "val_acc", value: 0.71,
    });
    await sidecar.pushEvent(runId, {
      seq: 1, epoch: 2, canonical_key: "val_accuracy", raw_key: "val_acc", value: 0.78, finished: true,
    });

    // What the panel's page reads, with no header, as an iframe on the sidecar.
    const run = await get(sidecar.port, `/api/runs/${runId}`);
    assert.strictEqual(run.status, 200, run.body);
    const metrics = await get(sidecar.port, `/api/metrics/${runId}`);
    assert.strictEqual(metrics.status, 200, metrics.body);
    const values = (JSON.parse(metrics.body) as { events: { value: number }[] }).events.map(
      (e) => e.value,
    );
    assert.deepStrictEqual(values, [0.71, 0.78]);

    // The extension host's own environment is left as it was.
    assert.strictEqual(process.env.EPOCHIX_AUTH_TOKEN, "exported-for-a-remote-server");
  });

  test("everything else in the environment still reaches the sidecar", () => {
    const env = sidecarEnv(
      { PATH: "/bin", EPOCHIX_DB: "/x/runs.db", EPOCHIX_AUTH_TOKEN: "t", EPOCHIX_CORS_ORIGINS: "*" },
      "/work/project",
    );
    assert.deepStrictEqual(env, {
      PATH: "/bin",
      EPOCHIX_DB: "/x/runs.db",
      EPOCHIX_GRADE_CONFIG: "/work/project",
      // Empty, not removed: an empty variable also outranks a `.env` file
      // that sets one.
      EPOCHIX_AUTH_TOKEN: "",
      EPOCHIX_CORS_ORIGINS: "",
    });
    assert.strictEqual(sidecarEnv({ PATH: "/bin" }).EPOCHIX_GRADE_CONFIG, undefined);
  });
});
