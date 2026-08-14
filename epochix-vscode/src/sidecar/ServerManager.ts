/**
 * ServerManager — spawn, monitor, and kill the Python epochix sidecar.
 *
 * Usage:
 *   const sidecar = await ServerManager.maybeStart(cfg);
 *   if (sidecar) { ... use sidecar.port ... }
 */
import * as vscode from "vscode";
import { ChildProcess, spawn } from "child_process";
import { resolveEpochix } from "./which";
import { candidateInterpreters } from "./interpreters";
import { findFreePort } from "./PortAllocator";
import { waitReady } from "./HealthCheck";
import { openExternalUrl } from "../util/uri";
import * as http from "http";
import * as os from "os";

export class ServerManager implements vscode.Disposable {
  readonly port: number;

  /**
   * Version of the Python package answering on `port`, once known.
   *
   * The staleness check already fetches this; keeping it means the bug
   * report can state it instead of asking the reporter to run `pip show`.
   * A stale sidecar silently degrades the whole product, so it is the
   * first thing worth knowing about a report.
   */
  static lastKnownSidecarVersion: string | undefined;
  private readonly _proc: ChildProcess;

  private constructor(proc: ChildProcess, port: number) {
    this._proc = proc;
    this.port = port;
  }

  // ── Factory ──────────────────────────────────────────────────────────────────

  /**
   * Start the sidecar if the user has epochix on PATH (or configured path).
   * Returns null if in standalone mode (useSidecar = "never" or not found).
   */
  static async maybeStart(
    cfg: vscode.WorkspaceConfiguration,
  ): Promise<ServerManager | null> {
    const mode = cfg.get<string>("useSidecar", "auto");
    if (mode === "never") return null;

    // An untrusted workspace must never make us execute an interpreter found
    // inside it — a hostile repo can ship a .venv whose `python` is anything.
    // Standalone mode is pure JS in the extension host, so it stays available.
    if (!vscode.workspace.isTrusted) {
      return null;
    }

    const binOverride = cfg.get<string>("sidecarPath", "");

    const resolved = await resolveEpochix(
      binOverride,
      await candidateInterpreters(),
    );
    if (!resolved) {
      if (mode === "always") {
        void vscode.window
          .showErrorMessage(
            "Epochix: cannot find the `epochix` Python package. The extension " +
              "works without it — it just cannot save run history. Install it " +
              "with `pip install epochix`, or point `epochix.sidecarPath` at " +
              "the executable if it is already installed somewhere unusual.",
            "Open Settings",
          )
          .then((choice) => {
            if (choice === "Open Settings") {
              void vscode.commands.executeCommand(
                "workbench.action.openSettings",
                "epochix.sidecarPath",
              );
            }
          });
      }
      return null; // standalone mode
    }
    const [cmd, prefix] = resolved;

    try {
      const port = await findFreePort(7860);

      // Only flags `epochix serve` actually accepts: --port / --host /
      // --log-level. (It never opens a browser, and the webview sets its own
      // locale, so the old --no-browser / --locale flags were bogus and made
      // the spawn fail.)
      const proc = spawn(
        cmd,
        [...prefix, "serve", "--port", String(port)],
        {
          detached: false,
          stdio: ["ignore", "pipe", "pipe"],
          windowsHide: true,
          // Never inherit the extension host's working directory. On Windows
          // that is the VS Code *installation* folder, and a running process
          // holds a lock on its own cwd — which is enough to make VS Code's
          // updater fail with "the process cannot access the file because it
          // is being used by another process". An editor extension must not be
          // able to block the editor's own update.
          cwd: os.tmpdir(),
        },
      );

      proc.on("error", (err) => {
        void vscode.window.showErrorMessage(
          `Epochix sidecar failed to start: ${err.message}`,
        );
      });

      await waitReady(`http://127.0.0.1:${port}/api/health`, 10_000);
      void warnIfSidecarIsStale(port);
      return new ServerManager(proc, port);
    } catch (err) {
      void vscode.window.showWarningMessage(
        `Epochix: Sidecar failed to start (${String(err)}). Running in standalone mode.`,
      );
      return null;
    }
  }

  // ── Public methods ───────────────────────────────────────────────────────────

  /**
   * POST JSON to the sidecar and return the decoded body.
   *
   * Checks the status code. The previous version did not, so any error whose
   * body happened to be JSON — a 404 is `{"detail":"Not Found"}` — decoded
   * cleanly, produced no `run_id`, and surfaced as "No run_id in response".
   * That masked a missing route for as long as it existed; a failure should
   * name itself.
   */
  private _post(path: string, payload: unknown): Promise<Record<string, unknown>> {
    return new Promise((resolve, reject) => {
      const body = JSON.stringify(payload);
      const req = http.request(
        `http://127.0.0.1:${this.port}${path}`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Content-Length": Buffer.byteLength(body),
          },
        },
        (res) => {
          let data = "";
          res.on("data", (chunk: Buffer) => { data += chunk.toString(); });
          res.on("end", () => {
            const code = res.statusCode ?? 0;
            if (code < 200 || code >= 300) {
              reject(new Error(`POST ${path} → HTTP ${code}: ${data.slice(0, 200)}`));
              return;
            }
            try {
              resolve(data ? (JSON.parse(data) as Record<string, unknown>) : {});
            } catch {
              reject(new Error(`POST ${path} → unparseable body: ${data.slice(0, 200)}`));
            }
          });
        },
      );
      req.on("error", reject);
      req.write(body);
      req.end();
    });
  }

  /** Create a run and return its id. */
  async createRun(
    name: string,
    task?: string,
    architecture?: unknown[],
    primaryMetric?: string | null,
  ): Promise<string> {
    const res = await this._post("/api/runs", {
      name,
      task,
      architecture: architecture?.length ? architecture : undefined,
      primary_metric: primaryMetric || undefined,
    });
    const id = res["id"] ?? res["run_id"];
    if (typeof id !== "string") {
      throw new Error(`POST /api/runs returned no id: ${JSON.stringify(res).slice(0, 200)}`);
    }
    return id;
  }

  /** Push one already-normalised metric event onto a run. */
  async pushEvent(runId: string, event: SidecarEvent): Promise<void> {
    await this._post(`/api/runs/${encodeURIComponent(runId)}/event`, event);
  }

  /**
   * Kill the sidecar, and on Windows its whole tree.
   *
   * `ChildProcess.kill()` signals only the direct child. `epochix serve` is a
   * Python process that may own further children, and a survivor keeps its cwd
   * locked and its port bound long after VS Code has gone — an orphaned
   * sidecar was observed still running with no Code.exe on the machine at all.
   * `taskkill /T /F` is the only reliable way to take the tree down on Windows.
   */
  dispose(): void {
    const pid = this._proc.pid;
    try {
      this._proc.kill();
    } catch {
      // already dead
    }
    if (process.platform === "win32" && pid !== undefined) {
      try {
        spawn("taskkill", ["/pid", String(pid), "/T", "/F"], {
          stdio: "ignore",
          windowsHide: true,
        });
      } catch {
        // best effort — the direct kill above may already have done it
      }
    }
  }
}

/** Matches the server's `EventPushRequest`. */
export interface SidecarEvent {
  seq: number;
  epoch?: number | null;
  step?: number | null;
  canonical_key: string;
  raw_key: string;
  value: number;
  unit?: string | null;
  /** Set on the final event so the server can finalise the run's summary. */
  finished?: boolean;
}


/**
 * Tell the user when the Python package is far older than the extension.
 *
 * The launcher resolves whichever interpreter it can find, and a machine can
 * easily have an ancient `pip install epochix` on PATH. Extension 0.5.36 was
 * observed driving a 0.5.0 sidecar: the dashboard silently lost features that
 * had shipped since — the architecture panel simply read "no architecture to
 * display" — and nothing anywhere said why.
 */
async function warnIfSidecarIsStale(port: number): Promise<void> {
  // (populates ServerManager.lastKnownSidecarVersion as a side effect)
  const sidecar = await fetchSidecarVersion(port);
  ServerManager.lastKnownSidecarVersion = sidecar ?? undefined;
  if (!sidecar) return;

  const ours = (vscode.extensions.getExtension("epochix.epochix")?.packageJSON as
    | { version?: string }
    | undefined)?.version;
  if (!ours || !isOlder(sidecar, ours)) return;

  void vscode.window
    .showWarningMessage(
      `Epochix: the Python package on this machine is ${sidecar}, but the ` +
        `extension is ${ours}. Features added since ${sidecar} will be missing ` +
        "or wrong. Update with `pip install -U epochix`.",
      "How do I fix this?",
    )
    .then((choice) => {
      if (choice === "How do I fix this?") {
        void openExternalUrl("https://epochix.dev/quickstart/");
      }
    });
}

function fetchSidecarVersion(port: number): Promise<string | null> {
  return new Promise((resolve) => {
    const req = http.get(
      `http://127.0.0.1:${port}/api/version`,
      { timeout: 3000 },
      (res) => {
        let data = "";
        res.on("data", (chunk: Buffer) => {
          data += chunk.toString();
        });
        res.on("end", () => {
          try {
            resolve((JSON.parse(data) as { version?: string }).version ?? null);
          } catch {
            resolve(null);
          }
        });
      },
    );
    req.on("error", () => resolve(null));
    req.on("timeout", () => {
      req.destroy();
      resolve(null);
    });
  });
}

/** Numeric semver compare, ignoring any pre-release suffix. */
export function isOlder(a: string, b: string): boolean {
  const parts = (v: string): number[] =>
    v
      .split("-")[0]
      .split(".")
      .map((n) => Number.parseInt(n, 10) || 0);
  const [x, y] = [parts(a), parts(b)];
  for (let i = 0; i < 3; i++) {
    if ((x[i] ?? 0) !== (y[i] ?? 0)) return (x[i] ?? 0) < (y[i] ?? 0);
  }
  return false;
}
