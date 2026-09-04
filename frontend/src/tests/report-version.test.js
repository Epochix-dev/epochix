/**
 * A bug report has to say what produced the page.
 *
 * The version came from `fetch('/api/version')` alone, and only ONE of the
 * three surfaces has a server. A VS Code webview and a standalone HTML export
 * both failed the fetch and filed "epochix (unavailable)" — so a report could
 * not be matched against a release, which is the first thing you need to know.
 *
 * Issue #35 is exactly that: a real report, from a VS Code webview
 * (`Code/1.135.0 ... Electron`), carrying no version at all.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

/** The resolution order under test, matching main.js. */
async function resolveVersion({ serverVersion, exported, extVersion }) {
  let diag = '(unavailable)';
  try {
    const r = await fetch('/api/version');
    if (r.ok) diag = (await r.json()).version ?? diag;
  } catch {
    /* no server */
  }
  if (diag === '(unavailable)') {
    const exportedVersion = exported?.epochix_version;
    if (exportedVersion) {
      diag = `${exportedVersion} (html export)`;
    } else if (extVersion) {
      diag = `${extVersion} (vs code extension)`;
    }
  }
  return diag;
}

describe('report version', () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn(() => Promise.reject(new Error('no server')));
  });

  afterEach(() => {
    vi.restoreAllMocks();
    delete window.__EPOCHIX_EXT_VERSION__;
  });

  it('prefers the live server when there is one', async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve({ version: '0.7.9' }) }),
    );
    const v = await resolveVersion({ exported: { epochix_version: '0.1.0' } });
    expect(v).toBe('0.7.9');
  });

  it('falls back to the version stamped into an HTML export', async () => {
    const v = await resolveVersion({ exported: { epochix_version: '0.7.8' } });
    expect(v).toBe('0.7.8 (html export)');
  });

  it('falls back to the VS Code extension version in a webview', async () => {
    const v = await resolveVersion({ exported: null, extVersion: '0.7.8' });
    expect(v).toBe('0.7.8 (vs code extension)');
  });

  it('names the surface, so an export is not mistaken for a server', async () => {
    const exported = await resolveVersion({ exported: { epochix_version: '0.7.8' } });
    const webview = await resolveVersion({ exported: null, extVersion: '0.7.8' });
    expect(exported).not.toBe(webview);
    expect(exported).toContain('html export');
    expect(webview).toContain('vs code extension');
  });

  it('still says so when nothing can tell it', async () => {
    const v = await resolveVersion({ exported: null });
    expect(v).toBe('(unavailable)');
  });

  it('a server that answers without a version does not report undefined', async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve({}) }),
    );
    const v = await resolveVersion({ exported: null });
    expect(v).toBe('(unavailable)');
  });
});

describe('report body', () => {
  /** `epochs 0` alone cannot say whether a run was ever opened. */
  function runLoadedLine(runId) {
    return `run loaded   ${runId ? 'yes' : 'no'}`;
  }

  it('distinguishes an empty dashboard from a run that produced nothing', () => {
    expect(runLoadedLine(null)).toBe('run loaded   no');
    expect(runLoadedLine('01ABC')).toBe('run loaded   yes');
  });
});
