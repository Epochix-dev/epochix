/**
 * The engine a dashboard panel reads a run with: the pinned task, the story's
 * language and the workspace's thresholds file.
 *
 * One place, so that whatever reads a terminal's output to say why no story
 * was told (terminal/CommandReading.ts) reads it exactly as the panel would.
 */
import { taskHint } from "../config";
import { workspaceGradeConfig } from "../gradeConfigFile";
import { StandaloneEngine } from "./StandaloneEngine";

export function panelEngine(locale: string): StandaloneEngine {
  return new StandaloneEngine(taskHint(), locale, workspaceGradeConfig());
}
