/**
 * Typed message protocol between the VS Code extension host and the WebView.
 *
 * Extension → WebView  (ExtToWeb)
 * WebView   → Extension (WebToExt)
 */

import type { Phase } from "../story/phases";
import type { Grade, TaskType } from "../story/grader";

// ── Shared data shapes ────────────────────────────────────────────────────────

export interface StoryFrameMsg {
  runId: string;
  seq: number;
  epoch: number | null;
  progress: number;
  phase: Phase;
  grade: Grade;
  primaryMetricValue: number;
  confidence: number;
  narrative: string;
  taskType: TaskType;
}

export interface MilestoneMsg {
  kind: string;
  epoch: number | null;
  message: string;
}

export interface WarningMsg {
  kind: string;
  epoch: number | null;
  message: string;
}

export interface RunSummaryMsg {
  id: string;
  name: string | null;
  taskType: TaskType;
  finalGrade: Grade | null;
  storySummary: string | null;
}

// ── Extension → WebView ───────────────────────────────────────────────────────

export type ExtToWeb =
  | {
      type: "init";
      theme: "light" | "dark";
      locale: string;
      snapshot: StoryFrameMsg[];
      milestones: MilestoneMsg[];
      warnings: WarningMsg[];
      hasSidecar: boolean;
    }
  | { type: "frame"; frame: StoryFrameMsg }
  | { type: "milestone"; milestone: MilestoneMsg }
  | { type: "warning"; warning: WarningMsg }
  | { type: "complete"; run: RunSummaryMsg }
  | { type: "themeChange"; theme: "light" | "dark" }
  | { type: "installBanner"; visible: boolean };

// ── WebView → Extension ───────────────────────────────────────────────────────

export type WebToExt =
  | { type: "ready" }
  | { type: "scrub"; seq: number }
  | { type: "export"; format: "html" | "pdf" | "md" }
  | { type: "openExternal"; url: string }
  | { type: "installSidecar" };
