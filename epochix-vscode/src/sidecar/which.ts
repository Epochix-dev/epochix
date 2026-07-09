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

/**
 * Resolve how to launch epochix, as [command, prefixArgs].
 *
 * Tries, in order:
 *   1. an explicit `epochix.sidecarPath` override,
 *   2. the `epochix` executable on PATH,
 *   3. `python -m epochix` (and `py` / `python3`) — covers the very common
 *      case where pip installed the console script under a Scripts/bin dir
 *      that isn't on PATH (especially Windows) while Python itself is.
 *
 * Returns null when epochix can't be found any of those ways.
 */
export async function resolveEpochix(
  override: string,
): Promise<[string, string[]] | null> {
  if (override) return [override, []];

  const direct = await which("epochix");
  if (direct) return [direct, []];

  for (const py of ["python", "py", "python3"]) {
    const pyPath = await which(py);
    if (pyPath && (await canImportEpochix(pyPath))) {
      return [pyPath, ["-m", "epochix"]];
    }
  }
  return null;
}

/** True if `<python> -c "import epochix"` exits 0. */
function canImportEpochix(python: string): Promise<boolean> {
  return new Promise((resolve) => {
    exec(`"${python}" -c "import epochix"`, (err) => resolve(!err));
  });
}
