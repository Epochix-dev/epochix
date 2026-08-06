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

/** Characters a browser discards from a URL before it parses the scheme. */
const URL_IGNORED = /[\u0000-\u0020\u007f]/g;

/** The only schemes this dashboard ever means to link to. */
const URL_SCHEMES = ['http', 'https', 'mailto'];

/**
 * Escape a value that reaches `href` or `src`, where escaping is not enough:
 * `javascript:` survives every entity substitution above.
 *
 * The check runs against what the BROWSER will see, not what we were handed.
 * Browsers strip tab, newline and carriage return from a URL before parsing
 * its scheme, so `java<TAB>script:alert(1)` arrives looking harmless and then
 * executes. A naive `/^[a-z][a-z0-9+.-]*:/` test was defeated by four such
 * payloads in a real DOM — tab, LF, CR, and a mixed-case variant.
 */
export function safeUrl(s) {
  const raw = String(s ?? '');

  // Over-stripping only ever makes this refuse more, which is the safe
  // direction for a URL.
  const probe = raw.replace(URL_IGNORED, '').toLowerCase();

  // Protocol-relative: `//evil.com` inherits the current scheme and navigates
  // off-site. Nothing in this dashboard means to do that.
  if (probe.startsWith('//')) return '#';

  const scheme = /^([a-z][a-z0-9+.-]*):/.exec(probe);
  if (scheme && !URL_SCHEMES.includes(scheme[1])) return '#';

  return escapeHtml(raw.trim());
}
