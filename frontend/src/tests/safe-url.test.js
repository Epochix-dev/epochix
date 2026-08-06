import { describe, it, expect } from 'vitest';
import { safeUrl, escapeHtml } from '../escape.js';

// safeUrl's first version tested the string it was handed. Browsers strip TAB,
// LF and CR from a URL *before* parsing its scheme, so `java<TAB>script:` was
// waved through and then executed. Four payloads defeated it in a real DOM.
//
// It was not called anywhere yet, which made it worse rather than better: an
// unused guard that does not guard is a trap for whoever reaches for it first.

const BYPASSES = [
  'java\tscript:alert(1)',
  'java\nscript:alert(1)',
  'java\rscript:alert(1)',
  'JaVa\tScRiPt:alert(1)',
  'java script:alert(1)',
  '\tjavascript:alert(1)',
];

const OUTRIGHT = ['javascript:alert(1)', 'data:text/html,<script>', 'vbscript:msgbox', '//evil.com'];

const LEGITIMATE = [
  'https://epochix.dev',
  'http://127.0.0.1:8420/runs/abc',
  '/runs/abc',
  'runs/abc.html',
  'mailto:hi@epochix.dev',
];

describe('safeUrl', () => {
  it.each(BYPASSES)('refuses %j, which a browser would read as javascript:', (evil) => {
    expect(safeUrl(evil)).toBe('#');
  });

  it.each(OUTRIGHT)('refuses %j', (evil) => {
    expect(safeUrl(evil)).toBe('#');
  });

  it.each(LEGITIMATE)('still allows %j', (url) => {
    expect(safeUrl(url)).not.toBe('#');
  });

  it('does not execute in a real anchor', () => {
    const a = document.createElement('a');
    a.setAttribute('href', safeUrl('java\tscript:alert(1)'));
    expect(a.protocol).not.toBe('javascript:');
  });

  it('handles non-strings without throwing', () => {
    for (const v of [null, undefined, 0, false, [], {}]) {
      expect(() => safeUrl(v)).not.toThrow();
    }
  });
});

describe('escape.js source hygiene', () => {
  it('escapes quotes as well as angle brackets', () => {
    expect(escapeHtml('"\'')).toBe('&quot;&#39;');
  });
});
