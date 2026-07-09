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
import { findFreePort } from "./PortAllocator";
import { waitReady } from "./HealthCheck";
import * as http from "http";

export class ServerManager implements vscode.Disposable {
  readonly port: number;
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

    const binOverride = cfg.get<string>("sidecarPath", "");

    const resolved = await resolveEpochix(binOverride);
    if (!resolved) {
      if (mode === "always") {
        void vscode.window.showErrorMessage(
          "Epochix: Cannot find the `epochix` package. Install it with " +
            "`pip install epochix`, or set `epochix.sidecarPath` to the " +
            "executable (e.g. …/Scripts/epochix.exe on Windows).",
        );
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
        },
      );

      proc.on("error", (err) => {
        void vscode.window.showErrorMessage(
          `Epochix sidecar failed to start: ${err.message}`,
        );
      });

      await waitReady(`http://127.0.0.1:${port}/api/health`, 10_000);
      return new ServerManager(proc, port);
    } catch (err) {
      void vscode.window.showWarningMessage(
        `Epochix: Sidecar failed to start (${String(err)}). Running in standalone mode.`,
      );
      return null;
    }
  }

  // ── Public methods ───────────────────────────────────────────────────────────

  /** Tell the sidecar to parse a log file and return the new run ID. */
  async parseLogFile(filePath: string): Promise<string> {
    return new Promise((resolve, reject) => {
      const url = `http://127.0.0.1:${this.port}/api/parse`;
      const body = JSON.stringify({ path: filePath });

      const req = http.request(
        url,
        { method: "POST", headers: { "Content-Type": "application/json" } },
        (res) => {
          let data = "";
          res.on("data", (chunk: Buffer) => { data += chunk.toString(); });
          res.on("end", () => {
            try {
              const parsed = JSON.parse(data) as { run_id?: string };
              if (parsed.run_id) resolve(parsed.run_id);
              else reject(new Error("No run_id in response"));
            } catch {
              reject(new Error(`Bad response: ${data}`));
            }
          });
        },
      );
      req.on("error", reject);
      req.write(body);
      req.end();
    });
  }

  /** Kill the sidecar process. */
  dispose(): void {
    try {
      this._proc.kill();
    } catch {
      // already dead
    }
  }
}
