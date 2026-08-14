import * as vscode from "vscode";

/**
 * Open an http(s) URL with its query exactly as it was built.
 *
 * `env.openExternal` is typed to take a `Uri`, and handing it one corrupts any
 * percent-encoded query. VS Code's opener (`_doOpenExternal`) picks between two
 * targets:
 *
 *     n = (typeof target === "string" && unchanged) ? target
 *                                                   : encodeURI(uri.toString(true));
 *
 * `Uri.toString(true)` writes the query back as raw text, and `encodeURI`
 * escapes `%`, so every escape that was already there gains a second round:
 * `%23` leaves as `%2523`. The prefilled bug report reached GitHub reading
 * `%23%23%23 What looks wrong%3F` instead of `### What looks wrong?`.
 *
 * Rebuilding the Uri cannot repair this, which is what the previous attempt
 * here did: `Uri` stores the query *decoded*, so parsing has already thrown the
 * encoding away and `Uri.from` puts back what `Uri.parse` produced — a no-op.
 * Plain `Uri.toString()` is worse again: it escapes the `&` and `=`
 * separators, so GitHub receives one nameless parameter and no `body` at all.
 *
 * Only the string branch survives. The extension host forwards the original
 * text alongside the parsed Uri (`$openUri(uri, uriAsString)`) and the opener
 * returns it untouched, which is why the cast below is the fix rather than a
 * shortcut. The published signature still says `Uri`; if a future release stops
 * accepting a string it rejects with "Invalid scheme - cannot be empty", so the
 * fallback keeps the link working instead of failing silently.
 */
export async function openExternalUrl(url: string): Promise<boolean> {
  try {
    return await vscode.env.openExternal(url as unknown as vscode.Uri);
  } catch {
    return await vscode.env.openExternal(vscode.Uri.parse(url));
  }
}

/**
 * Assemble a query from decoded pairs.
 *
 * Exists so the two bug-report builders encode identically, and so a test can
 * check what a reporter will actually see without launching a browser.
 */
export function buildUrl(base: string, params: Record<string, string>): string {
  const query = Object.entries(params)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
    .join("&");
  return query ? `${base}?${query}` : base;
}
