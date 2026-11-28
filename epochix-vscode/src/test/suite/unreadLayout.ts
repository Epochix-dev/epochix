/**
 * Output in a layout no reader takes, for the terminal notice's tests.
 *
 * Constructed here, not recorded, and not presented as any library's output:
 * a key/value table between rules of dashes with no section rows. It is the
 * shape a Stable-Baselines3 table had to Epochix before the SB3 parser read
 * it (that parser needs the section rows, `| rollout/ |`), and the notice's
 * tests used the real SB3 recording for it until then. A recorded training
 * layout that nothing reads would be better; none is in the repository now
 * (ROADMAP.md, "timm and MMEngine", are the likely ones).
 *
 * `loss` stands beside a different value in every table, so the notice has a
 * recognised name to quote; `value_loss` beside another.
 */
export function unreadTable(tables: number): string {
  let text = "";
  for (let i = 0; i < tables; i++) {
    const rule = "-".repeat(32);
    text += `${rule}\n`;
    text += `|    loss          | ${(7.28 / (i + 1)).toFixed(4).padEnd(9)}|\n`;
    text += `|    value_loss    | ${(49.1 / (i + 1)).toFixed(3).padEnd(9)}|\n`;
    text += `${rule}\n`;
  }
  return text;
}

/** How many different values `loss` takes in `unreadTable(tables)`. */
export function unreadLosses(tables: number): number {
  return new Set(Array.from({ length: tables }, (_, i) => (7.28 / (i + 1)).toFixed(4))).size;
}
