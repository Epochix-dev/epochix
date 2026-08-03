import * as vscode from "vscode";

/**
 * Build a Uri whose query survives `openExternal` unchanged.
 *
 * `vscode.Uri.parse(url)` treats an already percent-encoded query as literal
 * text and encodes it a second time, so `%23` becomes `%2523` and the target
 * site shows the escape rather than the character. That shipped once: the
 * prefilled bug report arrived as `%23%23%23 What looks wrong%3F` and the
 * mangled `labels=` made GitHub open a blank issue instead of the template.
 *
 * Decoding the query once and handing the raw string to `Uri.from` leaves
 * exactly one round of encoding.
 *
 * Lives here rather than beside its first caller so the second caller imports
 * it instead of copying it. The dashboard shipped twelve copies of an escape
 * helper that way, and every one of them was wrong.
 */
export function uriPreservingQuery(url: string): vscode.Uri {
  const parsed = vscode.Uri.parse(url);
  if (!parsed.query) {
    return parsed;
  }
  return vscode.Uri.from({
    scheme: parsed.scheme,
    authority: parsed.authority,
    path: parsed.path,
    query: decodeURIComponent(parsed.query),
    fragment: parsed.fragment,
  });
}
