/**
 * The story panel with nothing to tell says which kind of nothing it is.
 *
 * It said "Waiting for training data…" in every case — including a VS Code
 * dashboard opened with nothing attached, which waited forever, and a log that
 * held no metrics at all. A user reported exactly that screen (issue #35):
 * "epochs 0", no metric, no task, and no way to tell the two apart.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';

import { emptyState, EMPTY_STATE_COMMANDS } from '../panels/emptyState.js';

describe('emptyState', () => {
  it('a run with frames tells its story', () => {
    expect(emptyState({ frames: [{}], live: true })).toBe('story');
  });
  it('a VS Code panel with nothing attached says so', () => {
    expect(emptyState({ host: 'vscode', attached: false, live: true, frames: [] })).toBe('nothing-attached');
  });
  it('a live run that has not printed a metric yet is waiting', () => {
    expect(emptyState({ host: 'vscode', attached: true, live: true, frames: [] })).toBe('waiting');
    expect(emptyState({ live: true, frames: [] })).toBe('waiting');
  });
  it('a finished run with no metrics says no metrics were found', () => {
    expect(emptyState({ host: 'vscode', attached: true, live: false, run: { id: 'r' }, frames: [] }))
      .toBe('no-metrics');
    expect(emptyState({ live: false, run: { id: 'r' }, frames: [] })).toBe('no-metrics');
  });
});

describe('the empty VS Code panel', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="narrative-text"></div>';
  });

  it('offers the three ways in, and a click asks the host to run one', async () => {
    const { JourneyPanel } = await import('../panels/JourneyPanel.js');
    const posted = [];
    const listener = (ev) => posted.push(ev.detail.command);
    window.addEventListener('ms-run-command', listener);

    const store = { subscribe: () => () => {}, get: () => ({}) };
    const panel = Object.create(JourneyPanel.prototype);
    panel._store = store;
    panel._i18n = {};
    panel._render({ host: 'vscode', attached: false, live: true, frames: [], currentFrame: null, run: null });

    const buttons = [...document.querySelectorAll('.empty-action')];
    expect(buttons.map((b) => b.dataset.command)).toEqual(EMPTY_STATE_COMMANDS);
    buttons[0].click();
    expect(posted).toEqual(['epochix.tryDemo']);
    expect(document.querySelector('#narrative-text').textContent).not.toMatch(/Waiting/);
    window.removeEventListener('ms-run-command', listener);
  });

  it('a log with no metrics does not claim data is on its way', async () => {
    const { JourneyPanel } = await import('../panels/JourneyPanel.js');
    const panel = Object.create(JourneyPanel.prototype);
    panel._i18n = {};
    panel._render({ host: 'vscode', attached: true, live: false, frames: [], currentFrame: null, run: { id: 'r' } });
    const text = document.querySelector('#narrative-text').textContent;
    expect(text).toMatch(/No training metrics were found/);
    expect(text).not.toMatch(/Waiting/);
  });
});

describe('the bridge relays an empty-state command to the host', () => {
  it('posts runCommand', async () => {
    vi.resetModules();
    const sent = [];
    window.__EPOCHIX_VSCODE__ = { postMessage: (m) => sent.push(m) };
    const { startVscodeBridge } = await import('../vscode-bridge.js');
    expect(startVscodeBridge(() => {})).toBe(true);
    window.dispatchEvent(new CustomEvent('ms-run-command', { detail: { command: 'epochix.openLogFile' } }));
    expect(sent).toContainEqual({ type: 'runCommand', command: 'epochix.openLogFile' });
    delete window.__EPOCHIX_VSCODE__;
  });
});
