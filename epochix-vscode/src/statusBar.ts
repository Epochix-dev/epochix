/**
 * Status bar pill — a persistent, clickable entry point to the dashboard.
 *
 * Shown from activation onward (idle), then enriched with the live grade +
 * phase while a run streams. It used to be created hidden and only shown by
 * update() — which the DashboardPanel only calls once the dashboard is already
 * open — so on a fresh session there was no visible way to open the dashboard
 * at all (only the Ctrl+Alt+M keybinding or the command palette).
 *
 * Usage:
 *   StatusBar.init(context);
 *   StatusBar.update(frame);   // called by DashboardPanel on each new frame
 *   StatusBar.clear();         // called when dashboard closes → back to idle
 */
import * as vscode from "vscode";
import type { StoryFrameMsg } from "./webview/messages";
import { PHASE_EMOJIS } from "./story/phases";
import { gradeColor } from "./story/grader";

const IDLE_TEXT = "$(zap) Epochix";
const IDLE_TOOLTIP = "Epochix — click to open the dashboard";

let _item: vscode.StatusBarItem | undefined;

function _idle(): void {
  if (!_item) return;
  _item.text = IDLE_TEXT;
  _item.tooltip = IDLE_TOOLTIP;
  _item.color = undefined;
  _item.show();
}

export const StatusBar = {
  init(ctx: vscode.ExtensionContext): void {
    _item = vscode.window.createStatusBarItem(
      vscode.StatusBarAlignment.Right,
      100,
    );
    _item.command = "epochix.openDashboard";
    ctx.subscriptions.push(_item);
    _idle(); // visible immediately, so there's always a way in
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
    // Fall back to the idle pill rather than hiding — keep the entry point.
    _idle();
  },
};
