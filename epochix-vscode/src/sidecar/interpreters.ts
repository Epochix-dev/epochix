/**
 * Python interpreters the EDITOR knows about but the shell may not.
 *
 * The single most common reason "Try a Demo Run" failed on a fresh machine:
 * epochix is installed in a virtualenv, so neither `epochix` nor a bare
 * `python` is on PATH, and the extension told the user to install a package
 * they already had. VS Code almost always knows the right interpreter — the
 * Python extension tracks the selected one, and workspace venvs sit in
 * predictable places.
 */
import * as vscode from "vscode";
import * as fs from "fs";
import * as path from "path";

/** Relative paths to a venv interpreter, per platform. */
const VENV_BIN =
  process.platform === "win32"
    ? ["Scripts", "python.exe"]
    : ["bin", "python"];

/** Directory names people actually use for a project virtualenv. */
const VENV_DIRS = [".venv", "venv", "env", ".env"];

/**
 * Candidate interpreters, best guess first, de-duplicated.
 *
 * Never throws: every source is optional and a failure to read one must not
 * stop the others from being tried.
 */
export async function candidateInterpreters(): Promise<string[]> {
  const found: string[] = [];

  const add = (p: string | undefined | null): void => {
    if (!p) return;
    if (!found.includes(p) && fs.existsSync(p)) found.push(p);
  };

  // 1. The interpreter the user selected in the Python extension.
  try {
    const ext = vscode.extensions.getExtension("ms-python.python");
    if (ext) {
      if (!ext.isActive) await ext.activate();
      const api = ext.exports as {
        environments?: {
          getActiveEnvironmentPath?: () => { path?: string } | undefined;
        };
      };
      add(api?.environments?.getActiveEnvironmentPath?.()?.path);
    }
  } catch {
    // Python extension missing or its API changed — keep going.
  }

  // 2. An explicitly configured default interpreter.
  try {
    add(
      vscode.workspace
        .getConfiguration("python")
        .get<string>("defaultInterpreterPath"),
    );
  } catch {
    // no workspace / setting unavailable
  }

  // 3. Virtualenvs sitting in an open workspace folder.
  for (const folder of vscode.workspace.workspaceFolders ?? []) {
    for (const dir of VENV_DIRS) {
      add(path.join(folder.uri.fsPath, dir, ...VENV_BIN));
    }
  }

  return found;
}
