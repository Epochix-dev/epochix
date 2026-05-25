/**
 * Typed wrapper around vscode.workspace.getConfiguration("modelStory").
 */
import * as vscode from "vscode";

export interface ModelStoryConfig {
  autoWatchTerminal: boolean;
  taskHint: "auto" | "classification" | "detection" | "regression" | "biometric" | "gaze" | "nlp";
  useSidecar: "auto" | "always" | "never";
  sidecarPath: string;
  llmFallback: boolean;
  theme: "auto" | "light" | "dark";
  locale: "en" | "fa" | "fr";
}

export function getConfig(): ModelStoryConfig {
  const cfg = vscode.workspace.getConfiguration("modelStory");
  return {
    autoWatchTerminal: cfg.get<boolean>("autoWatchTerminal", true),
    taskHint: cfg.get<ModelStoryConfig["taskHint"]>("taskHint", "auto"),
    useSidecar: cfg.get<ModelStoryConfig["useSidecar"]>("useSidecar", "auto"),
    sidecarPath: cfg.get<string>("sidecarPath", ""),
    llmFallback: cfg.get<boolean>("llmFallback", false),
    theme: cfg.get<ModelStoryConfig["theme"]>("theme", "auto"),
    locale: cfg.get<ModelStoryConfig["locale"]>("locale", "en"),
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
