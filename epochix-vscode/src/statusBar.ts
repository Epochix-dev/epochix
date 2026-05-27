/**
 * Status bar pill — shows the current grade + phase emoji.
 * Clicking opens the dashboard.
 *
 * Usage:
 *   StatusBar.init(context);
 *   StatusBar.update(frame);   // called by DashboardPanel on each new frame
 *   StatusBar.clear();         // called when dashboard closes
 */
import * as vscode from "vscode";
import type { StoryFrameMsg } from "./webview/messages";
import { PHASE_EMOJIS } from "./story/phases";
import { gradeColor } from "./story/grader";

let _item: vscode.StatusBarItem | undefined;

export const StatusBar = {
  init(ctx: vscode.ExtensionContext): void {
    _item = vscode.window.createStatusBarItem(
      vscode.StatusBarAlignment.Right,
      100,
    );
    _item.command = "epochix.openDashboard";
    _item.tooltip = "Epochix — click to open dashboard";
    ctx.subscriptions.push(_item);
  },

  update(frame: StoryFrameMsg): void {
    if (!_item) return;
    const emoji = PHASE_EMOJIS[frame.phase] ?? "📈";
    _item.text = `$(zap) ${emoji} ${frame.grade}`;
    _item.tooltip = `Epochix · ${frame.narrative.slice(0, 80)}`;
    _item.color = gradeColor(frame.grade);
    _item.show();
  },

  clear(): void {
    _item?.hide();
  },
};
