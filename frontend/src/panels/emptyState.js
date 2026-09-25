/**
 * What an empty story panel should say.
 *
 * It said "Waiting for training data…" in every case. That is true of exactly
 * one: a live run that has not printed a metric yet. A VS Code dashboard opened
 * with nothing attached waited forever for data nothing would send, and a log
 * that was read through and held no metrics claimed data was still coming —
 * both arrived as bug reports with "epochs 0" and nothing else to go on
 * (issue #35).
 *
 * @param {{ host?: string, attached?: boolean, live?: boolean, run?: object|null, frames?: object[] }} s
 * @returns {'story'|'waiting'|'nothing-attached'|'no-metrics'}
 */
export function emptyState(s) {
  if (s.frames && s.frames.length > 0) return 'story';
  if (s.host === 'vscode' && !s.attached) return 'nothing-attached';
  if (s.live) return 'waiting';
  if (s.run) return 'no-metrics';
  return 'waiting';
}

/** Commands the empty VS Code dashboard offers — the host allows only these. */
export const EMPTY_STATE_COMMANDS = ['epochix.tryDemo', 'epochix.openLogFile', 'epochix.watchTerminal'];
