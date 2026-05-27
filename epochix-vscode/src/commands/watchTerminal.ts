import * as vscode from "vscode";
import type { TerminalWatcher } from "../terminal/TerminalWatcher";

export function registerWatchTerminal(
  watcher: TerminalWatcher,
): vscode.Disposable {
  return vscode.commands.registerCommand("epochix.watchTerminal", () => {
    watcher.attachToActive();
  });
}
