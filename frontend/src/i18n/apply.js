/**
 * i18n/apply.js — localise the static HTML chrome and set text direction.
 *
 * Elements carry `data-i18n="dotted.key"` (sets textContent) or
 * `data-i18n-title="dotted.key"` (sets the title attribute). Missing keys fall
 * back to the hardcoded English already in the markup, so a partial translation
 * degrades gracefully rather than blanking. Locales in `RTL_LOCALES` flip the
 * document to right-to-left.
 */

export const RTL_LOCALES = new Set(['fa']);

/** Resolve a dotted path ("ui.nav.overview") against a nested dict. */
export function resolveKey(dict, path) {
  return path.split('.').reduce((o, k) => (o && o[k] != null ? o[k] : null), dict);
}

/**
 * @param {object} i18n    loaded locale dictionary
 * @param {string} locale  locale code (e.g. "en", "fr", "fa")
 * @param {Document} [doc] document to operate on (injectable for tests)
 */
export function applyStaticI18n(i18n, locale, doc = document) {
  const root = doc.documentElement;
  root.lang = locale;
  root.dir = RTL_LOCALES.has(locale) ? 'rtl' : 'ltr';

  for (const el of doc.querySelectorAll('[data-i18n]')) {
    const v = resolveKey(i18n, el.getAttribute('data-i18n'));
    if (typeof v === 'string') el.textContent = v;
  }
  for (const el of doc.querySelectorAll('[data-i18n-title]')) {
    const v = resolveKey(i18n, el.getAttribute('data-i18n-title'));
    if (typeof v === 'string') el.title = v;
  }
}
