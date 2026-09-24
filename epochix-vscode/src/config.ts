/**
 * Typed wrapper around vscode.workspace.getConfiguration("epochix").
 */
import * as vscode from "vscode";

import type { TaskType } from "./story/grader";

export interface EpochixConfig {
  autoWatchTerminal: boolean;
  taskHint: "auto" | Exclude<TaskType, "custom">;
  useSidecar: "auto" | "always" | "never";
  sidecarPath: string;
  theme: "auto" | "light" | "dark";
  locale: "en" | "fa" | "fr";
}

export function getConfig(): EpochixConfig {
  const cfg = vscode.workspace.getConfiguration("epochix");
  return {
    autoWatchTerminal: cfg.get<boolean>("autoWatchTerminal", true),
    taskHint: cfg.get<EpochixConfig["taskHint"]>("taskHint", "auto"),
    useSidecar: cfg.get<EpochixConfig["useSidecar"]>("useSidecar", "auto"),
    sidecarPath: cfg.get<string>("sidecarPath", ""),
    theme: cfg.get<EpochixConfig["theme"]>("theme", "auto"),
    locale: cfg.get<EpochixConfig["locale"]>("locale", "en"),
  };
}

/** The task the user pinned in settings, or undefined to detect it from the log. */
export function taskHint(): TaskType | undefined {
  const hint = getConfig().taskHint;
  return hint === "auto" ? undefined : hint;
}

export function resolvedTheme(): "light" | "dark" {
  const cfg = getConfig();
  if (cfg.theme === "light") return "light";
  if (cfg.theme === "dark") return "dark";
  // auto: follow VS Code's active theme
  return vscode.window.activeColorTheme.kind === vscode.ColorThemeKind.Light
    ? "light"
    : "dark";
}
