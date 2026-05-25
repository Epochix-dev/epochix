/**
 * Cross-platform `which` — find an executable on PATH.
 * Returns the full path or null if not found.
 */
import { exec } from "child_process";

export function which(bin: string): Promise<string | null> {
  const cmd = process.platform === "win32" ? `where ${bin}` : `which ${bin}`;
  return new Promise((resolve) => {
    exec(cmd, (err, stdout) => {
      if (err) {
        resolve(null);
      } else {
        // `where` may return multiple paths — take the first
        resolve(stdout.trim().split(/\r?\n/)[0] || null);
      }
    });
  });
}
