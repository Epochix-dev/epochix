/**
 * ServerManager — spawn, monitor, and kill the Python model-story sidecar.
 *
 * Usage:
 *   const sidecar = await ServerManager.maybeStart(cfg);
 *   if (sidecar) { ... use sidecar.port ... }
 */
import * as vscode from "vscode";
import { ChildProcess, spawn } from "child_process";
import { which } from "./which";
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
   * Start the sidecar if the user has model-story on PATH (or configured path).
   * Returns null if in standalone mode (useSidecar = "never" or not found).
   */
  static async maybeStart(
    cfg: vscode.WorkspaceConfiguration,
  ): Promise<ServerManager | null> {
    const mode = cfg.get<string>("useSidecar", "auto");
    if (mode === "never") return null;

    const binOverride = cfg.get<string>("sidecarPath", "");
    const bin = binOverride || "model-story";

    const found = await which(bin);
    if (!found) {
      if (mode === "always") {
        void vscode.window.showErrorMessage(
          `Model Story: Cannot find '${bin}'. ` +
            `Install with: pip install model-story`,
        );
      }
      return null; // standalone mode
    }

    try {
      const port = await findFreePort(7860);
      const locale = cfg.get<string>("locale", "en");

      const proc = spawn(
        found,
        ["serve", "--port", String(port), "--no-browser", "--locale", locale],
        {
          detached: false,
          stdio: ["ignore", "pipe", "pipe"],
          windowsHide: true,
        },
      );

      proc.on("error", (err) => {
        void vscode.window.showErrorMessage(
          `Model Story sidecar failed to start: ${err.message}`,
        );
      });

      await waitReady(`http://127.0.0.1:${port}/api/health`, 10_000);
      return new ServerManager(proc, port);
    } catch (err) {
      void vscode.window.showWarningMessage(
        `Model Story: Sidecar failed to start (${String(err)}). Running in standalone mode.`,
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
