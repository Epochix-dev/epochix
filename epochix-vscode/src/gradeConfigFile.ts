/**
 * Finding and reading a workspace's `.epochix.yaml`.
 *
 * The command line looks in the folder it is run from, then each parent, then
 * `~/.epochix/.epochix.yaml` (config_loader.find_config_file). An editor has
 * no such folder, so the search starts at the workspace's first folder — the
 * project root, which is where a person runs `epochix` from.
 */
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import * as vscode from "vscode";

import { parseGradeConfig, type GradeConfig } from "./story/gradeConfig";

const FILENAME = ".epochix.yaml";

function isFile(candidate: string): boolean {
  try {
    return fs.statSync(candidate).isFile();
  } catch {
    return false;
  }
}

/** The nearest `.epochix.yaml` at or above `start`, else the per-user one, else null. */
export function findGradeConfigFile(start: string | undefined, home: string | undefined): string | null {
  if (start) {
    let dir = path.resolve(start);
    for (;;) {
      const candidate = path.join(dir, FILENAME);
      if (isFile(candidate)) return candidate;
      const parent = path.dirname(dir);
      if (parent === dir) break;
      dir = parent;
    }
  }
  if (home) {
    const candidate = path.join(home, ".epochix", FILENAME);
    if (isFile(candidate)) return candidate;
  }
  return null;
}

/** The thresholds in the file at `file`, or null when it sets nothing or cannot be read. */
export function readGradeConfigFile(file: string): GradeConfig | null {
  let text: string;
  try {
    text = fs.readFileSync(file, "utf8");
  } catch {
    return null;
  }
  return parseGradeConfig(text, file).config;
}

function homeDir(): string | undefined {
  try {
    return os.homedir() || undefined;
  } catch {
    return undefined; // a stripped environment has no home to look in
  }
}

/** The thresholds file a run in this window is graded with, or null. */
export function workspaceGradeConfigFile(): string | null {
  const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  return findGradeConfigFile(root, homeDir());
}

/** The thresholds a run in this window is graded with, or null for the built-in ones. */
export function workspaceGradeConfig(): GradeConfig | null {
  const file = workspaceGradeConfigFile();
  return file === null ? null : readGradeConfigFile(file);
}
