import { describe, it, expect } from 'vitest';
import { escapeHtml, safeUrl } from '../escape.js';

// This file exists because of a real, confirmed XSS. Eleven copies of a local
// `_esc` escaped &, < and > but not quotes, and most of them were used inside
// attribute values. A run named `x" onmouseover="alert(1)` closed the title
// attribute and installed a live event handler — and run names come from log
// files, so a training script was enough to trigger it.

const ATTR_PAYLOADS = [
  'resnet" onmouseover="alert(1)',
  "resnet' onmouseover='alert(1)",
  'a"><script>alert(1)</script>',
  '<img src=x onerror=alert(1)>',
  '"><svg onload=alert(1)>',
];

describe('escapeHtml', () => {
  it.each(ATTR_PAYLOADS)('neutralises %j in an attribute value', (evil) => {
    const host = document.createElement('div');
    host.innerHTML = `<span class="n" title="${escapeHtml(evil)}">${escapeHtml(evil)}</span>`;

    const el = host.querySelector('.n');
    // Only the attributes we wrote may exist — an injected handler shows up here.
    expect([...el.attributes].map((a) => a.name).sort()).toEqual(['class', 'title']);
    expect(host.querySelectorAll('script, img, svg')).toHaveLength(0);
    // And the value must survive intact: escaping that mangles run names is
    // its own bug, since the name is what the user recognises the run by.
    expect(el.getAttribute('title')).toBe(evil);
    expect(el.textContent).toBe(evil);
  });

  it('escapes both quote characters', () => {
    expect(escapeHtml('"')).toBe('&quot;');
    expect(escapeHtml("'")).toBe('&#39;');
  });

  it('escapes the ampersand first, so entities are not double-decoded', () => {
    expect(escapeHtml('&lt;')).toBe('&amp;lt;');
  });

  it('renders null and undefined as empty, not as the words', () => {
    expect(escapeHtml(null)).toBe('');
    expect(escapeHtml(undefined)).toBe('');
  });

  it('leaves ordinary run names untouched', () => {
    expect(escapeHtml('resnet50-lr0.01_run2')).toBe('resnet50-lr0.01_run2');
  });
});

describe('safeUrl', () => {
  it.each(['javascript:alert(1)', 'JaVaScRiPt:alert(1)', 'data:text/html,<script>alert(1)</script>', 'vbscript:msgbox'])(
    'refuses %j',
    (evil) => {
      expect(safeUrl(evil)).toBe('#');
    },
  );

  it('allows the schemes the dashboard actually links to', () => {
    expect(safeUrl('https://epochix.dev')).toBe('https://epochix.dev');
    expect(safeUrl('http://127.0.0.1:8420/runs')).toBe('http://127.0.0.1:8420/runs');
    expect(safeUrl('/runs/abc')).toBe('/runs/abc');
  });
});
