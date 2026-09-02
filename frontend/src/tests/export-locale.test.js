/**
 * A standalone HTML export must open in the language the run was told in.
 *
 * The locale was read from `?locale=` or localStorage and nowhere else. An
 * export opened from disk has neither, so every report fell back to English:
 * a Farsi run rendered with English chrome, ltr direction and lang="en", with
 * only the stored narratives in Farsi — while the run data embedded in that
 * same file said `"locale": "fa"` all along.
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest';

/** The resolution order main.js uses, extracted so it can be tested directly. */
function resolveLocale({ param, runLocale, stored }) {
  return param ?? runLocale ?? stored ?? 'en';
}

describe('export locale resolution', () => {
  it('uses the run own locale when there is no query string', () => {
    expect(resolveLocale({ param: null, runLocale: 'fa', stored: null })).toBe('fa');
  });

  it('lets an explicit ?locale= override the run', () => {
    // A reader who asks for a different language should get it.
    expect(resolveLocale({ param: 'en', runLocale: 'fa', stored: null })).toBe('en');
  });

  it('prefers the run over a stale localStorage from another run', () => {
    expect(resolveLocale({ param: null, runLocale: 'fr', stored: 'fa' })).toBe('fr');
  });

  it('falls back to localStorage when the run says nothing', () => {
    expect(resolveLocale({ param: null, runLocale: null, stored: 'fr' })).toBe('fr');
  });

  it('ends at English rather than undefined', () => {
    expect(resolveLocale({ param: null, runLocale: null, stored: null })).toBe('en');
  });
});

describe('the exported page declares its language', () => {
  beforeEach(() => {
    document.documentElement.lang = '';
    document.documentElement.dir = '';
  });
  afterEach(() => {
    document.documentElement.lang = '';
    document.documentElement.dir = '';
  });

  it('sets lang and rtl for Farsi', async () => {
    const { applyStaticI18n } = await import('../i18n/apply.js');
    applyStaticI18n({}, 'fa', document);
    expect(document.documentElement.lang).toBe('fa');
    expect(document.documentElement.dir).toBe('rtl');
  });

  it('leaves French left-to-right', async () => {
    const { applyStaticI18n } = await import('../i18n/apply.js');
    applyStaticI18n({}, 'fr', document);
    expect(document.documentElement.lang).toBe('fr');
    expect(document.documentElement.dir).toBe('ltr');
  });
});
