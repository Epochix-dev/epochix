/**
 * Tests for i18n/apply.js — static-chrome localisation + text direction.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { applyStaticI18n, resolveKey, RTL_LOCALES } from '../i18n/apply.js';
import en from '../i18n/en.json';
import fr from '../i18n/fr.json';
import fa from '../i18n/fa.json';

function setupDom() {
  document.documentElement.lang = '';
  document.documentElement.dir = '';
  document.body.innerHTML = `
    <span data-i18n="ui.nav.overview">Overview</span>
    <span data-i18n="ui.panels.networkState">Network State</span>
    <span data-i18n="ui.does.not.exist">Fallback Text</span>
    <button data-i18n-title="ui.nav.engineer" title="Engineer">x</button>`;
}

describe('resolveKey', () => {
  it('resolves a dotted path', () => {
    expect(resolveKey({ a: { b: { c: 'v' } } }, 'a.b.c')).toBe('v');
  });
  it('returns null for a missing path (no throw)', () => {
    expect(resolveKey({ a: {} }, 'a.b.c')).toBeNull();
    expect(resolveKey({}, 'x.y')).toBeNull();
  });
});

describe('applyStaticI18n', () => {
  beforeEach(setupDom);

  it('translates data-i18n elements (English is identity)', () => {
    applyStaticI18n(en, 'en');
    expect(document.querySelector('[data-i18n="ui.nav.overview"]').textContent).toBe('Overview');
    expect(document.documentElement.lang).toBe('en');
    expect(document.documentElement.dir).toBe('ltr');
  });

  it('applies French translations + stays LTR', () => {
    applyStaticI18n(fr, 'fr');
    expect(document.querySelector('[data-i18n="ui.nav.overview"]').textContent).toBe('Aperçu');
    expect(document.querySelector('[data-i18n="ui.panels.networkState"]').textContent).toBe('État du réseau');
    expect(document.documentElement.dir).toBe('ltr');
  });

  it('applies Persian translations + flips to RTL', () => {
    applyStaticI18n(fa, 'fa');
    expect(document.querySelector('[data-i18n="ui.panels.networkState"]').textContent).toBe('وضعیت شبکه');
    expect(document.documentElement.dir).toBe('rtl');
    expect(document.documentElement.lang).toBe('fa');
  });

  it('leaves the hardcoded English fallback when a key is missing', () => {
    applyStaticI18n(fa, 'fa');
    expect(document.querySelector('[data-i18n="ui.does.not.exist"]').textContent).toBe('Fallback Text');
  });

  it('sets title attributes from data-i18n-title', () => {
    applyStaticI18n(fr, 'fr');
    expect(document.querySelector('[data-i18n-title]').title).toBe('Ingénieur');
  });

  it('only fa is registered as RTL', () => {
    expect(RTL_LOCALES.has('fa')).toBe(true);
    expect(RTL_LOCALES.has('en')).toBe(false);
    expect(RTL_LOCALES.has('fr')).toBe(false);
  });

  it('every data-i18n key in the markup exists in en.json', () => {
    // guard against a typo'd key silently falling back forever
    setupDom();
    for (const el of document.querySelectorAll('[data-i18n]')) {
      const key = el.getAttribute('data-i18n');
      if (key === 'ui.does.not.exist') continue; // the deliberate-miss fixture
      expect(resolveKey(en, key), `missing en key: ${key}`).toBeTypeOf('string');
    }
  });
});
