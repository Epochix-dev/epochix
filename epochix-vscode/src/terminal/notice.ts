/**
 * The status-bar item that says a watched command was seen and not told.
 *
 * A status-bar item, not a notification: it says it once, interrupts nothing,
 * and can be taken back when it stops being true — the dashboard opening for
 * that command after all withdraws it. Hovering shows the diagnosis; clicking
 * shows it as a message with, when the dashboard can tell the run, a button
 * that opens it. Never modal.
 *
 * Nothing here leaves the machine: the diagnosis is shown, never sent.
 */
import * as vscode from "vscode";

import type { CommandReading } from "./CommandReading";
import type { NoticeText } from "./noticeText";
import { message } from "../story/narrator";

interface Shown {
  reading: CommandReading;
  text: NoticeText;
  open: () => void;
}

/** What clicking the item runs; registered by extension.ts, which owns the
 *  one watcher whose notice it shows. */
export const NOTICE_COMMAND = "epochix.terminalNotice";

export class TerminalNotice implements vscode.Disposable {
  private _item: vscode.StatusBarItem | undefined;
  private _shown: Shown | null = null;

  constructor(private readonly _locale: string) {}

  /** What is on show, for tests: the item and the command it is about. */
  get shown(): { item: vscode.StatusBarItem; reading: CommandReading; text: NoticeText } | null {
    if (this._shown === null || this._item === undefined) return null;
    return { item: this._item, reading: this._shown.reading, text: this._shown.text };
  }

  show(reading: CommandReading, text: NoticeText, open: () => void): void {
    this._shown = { reading, text, open };
    const item = (this._item ??= vscode.window.createStatusBarItem(
      vscode.StatusBarAlignment.Right,
      99, // beside the Epochix pill (100)
    ));
    item.text = `${text.canOpen ? "$(graph)" : "$(question)"} ${text.status}`;
    const tooltip = new vscode.MarkdownString();
    for (const sentence of text.sentences) tooltip.appendText(sentence).appendMarkdown("\n\n");
    tooltip.appendText(message("term_click", this._locale));
    item.tooltip = tooltip;
    item.command = NOTICE_COMMAND;
    item.show();
  }

  /** Take the notice back — about `reading` only, when one is given. */
  withdraw(reading?: CommandReading): void {
    if (this._shown === null) return;
    if (reading !== undefined && this._shown.reading !== reading) return;
    this._shown = null;
    this._item?.hide();
  }

  /** Open the command's run in the dashboard, as the message's button does. */
  open(): void {
    const shown = this._shown;
    if (shown === null || !shown.text.canOpen) return;
    this.withdraw();
    shown.open();
  }

  async details(): Promise<void> {
    const shown = this._shown;
    if (shown === null) return;
    const label = message("term_action_open", this._locale);
    const choice = await vscode.window.showInformationMessage(
      shown.text.sentences.join(" "),
      ...(shown.text.canOpen ? [label] : []),
    );
    if (choice === label && this._shown === shown) this.open();
  }

  dispose(): void {
    this._item?.dispose();
    this._item = undefined;
    this._shown = null;
  }
}
