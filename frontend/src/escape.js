/**
 * HTML escaping for values interpolated into template strings.
 *
 * One implementation, imported everywhere. There used to be eleven copies of
 * a local `_esc`, and every one of them escaped `&`, `<` and `>` but not `"`.
 * That is safe in text position and an XSS hole in attribute position, which
 * is where most of them were used:
 *
 *     `<span title="${_esc(name)}">`
 *
 * A run named `x" onmouseover="alert(1)` closed the attribute and added a live
 * event handler. Run names come from log files, so this was reachable with a
 * training script that names a run — no access to the machine required, and it
 * fired inside the VS Code webview too.
 *
 * Escaping the quotes is what makes it safe in both positions, so there is one
 * function rather than an attribute variant nobody remembers to reach for.
 */
export function escapeHtml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/**
 * Escape a value used in an *unquoted* attribute or a URL-ish attribute.
 *
 * Prefer quoting the attribute and using `escapeHtml`. This exists for the
 * cases where the value reaches `href`/`src`, where escaping is not enough on
 * its own: `javascript:` survives every entity substitution above.
 */
export function safeUrl(s) {
  const raw = String(s ?? '').trim();
  // Scheme-relative and absolute URLs with a scheme we did not vet are the
  // problem; anything relative is fine.
  if (/^[a-z][a-z0-9+.-]*:/i.test(raw)) {
    const scheme = raw.slice(0, raw.indexOf(':')).toLowerCase();
    if (scheme !== 'http' && scheme !== 'https' && scheme !== 'mailto') return '#';
  }
  return escapeHtml(raw);
}
