/**
 * The words of the terminal notice (terminal/notice.ts), in the story's
 * language. Pure, so every verdict can be rendered in every language in a test.
 *
 * The sentences live in the Python catalogue (story_engine/messages.py,
 * `term_*`) and are generated into narratives.generated.ts, so all three
 * languages are checked for the same placeholders. Every number filled in is
 * a count from the command's own output; nothing else is said.
 */
import { message } from "../story/narrator";
import type { Verdict } from "./CommandReading";

export interface NoticeText {
  /** The status-bar item's label. */
  status: string;
  /** The diagnosis, sentence by sentence. */
  sentences: string[];
  /** Whether the dashboard can be offered: the run is told and wholly held. */
  canOpen: boolean;
}

// How a list of names is joined: Persian has its own comma. Punctuation, not
// a sentence, so it is not in the message catalogue.
const LIST_SEPARATOR: Readonly<Record<string, string>> = { fa: "، " };

export function noticeText(verdict: Verdict, locale: string): NoticeText {
  const say = (key: string, fields: Record<string, string> = {}): string =>
    message(key, locale, fields);
  const sep = LIST_SEPARATOR[locale] ?? ", ";
  const sentences: string[] = [];

  if (verdict.kind === "unopened") {
    sentences.push(say("term_title_unopened"));
    sentences.push(say("term_lines", { lines: String(verdict.lines) }));
    if (verdict.sampled !== null) {
      sentences.push(say("term_sampled", { sampled: String(verdict.sampled) }));
    }
    sentences.push(say("term_story", { metric: verdict.metric, count: String(verdict.count) }));
    if (verdict.complete) sentences.push(say("term_fix_open"));
    sentences.push(say("term_fix_check"));
    return { status: say("term_status_unopened"), sentences, canOpen: verdict.complete };
  }

  sentences.push(say(verdict.opened ? "term_title_opened_empty" : "term_title_unread"));
  sentences.push(say("term_lines", { lines: String(verdict.lines) }));
  if (verdict.sampled !== null) {
    sentences.push(say("term_sampled", { sampled: String(verdict.sampled) }));
  }
  if (verdict.readings.length > 0) {
    const readings = verdict.readings.map(([name, n]) => `${name} (${n})`).join(sep);
    sentences.push(say("term_read", { readings }));
  } else {
    sentences.push(say("term_read_none"));
  }
  if (verdict.labelled.length > 0) {
    const names = verdict.labelled
      .map(([name, n]) => say("term_values", { name, count: String(n) }))
      .join(sep);
    sentences.push(say("term_labelled", { names }));
  }
  sentences.push(say(verdict.readings.length > 0 ? "term_why_no_score" : "term_why_layout"));
  sentences.push(say("term_fix_print"));
  sentences.push(say("term_fix_check"));
  return { status: say("term_status_unread"), sentences, canOpen: false };
}
