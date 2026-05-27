/**
 * Typed wrapper around vscode.workspace.getConfiguration("epochix").
 */
import * as vscode from "vscode";

export interface EpochixConfig {
  autoWatchTerminal: boolean;
  taskHint: "auto" | "classification" | "detection" | "regression" | "biometric" | "gaze" | "nlp";
  useSidecar: "auto" | "always" | "never";
  sidecarPath: string;
  llmFallback: boolean;
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
    llmFallback: cfg.get<boolean>("llmFallback", false),
    theme: cfg.get<EpochixConfig["theme"]>("theme", "auto"),
    locale: cfg.get<EpochixConfig["locale"]>("locale", "en"),
  };
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
