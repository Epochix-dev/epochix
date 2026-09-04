import { describe, it, expect, vi, beforeEach } from 'vitest';
import { openIssue, reportFrame, frameReportButton } from '../report.js';

// The per-frame "this looks wrong" control (#56). It exists because this
// product's characteristic failure is a WRONG NUMBER, not a crash — the page
// renders perfectly and states something false. A report therefore has to pin
// down which reading, which the whole-dashboard button cannot do.

const FRAME = {
  epoch: 14,
  primary_metric: 'val_accuracy',
  primary_metric_value: 0.761,
  grade: 'B',
  phase: 'polishing',
  narrative: 'The model holds at 76.1% — steady, if not improving.',
};
const RUN = { name: 'my-secret-project', task_type: 'classification', primary_metric: 'val_accuracy' };

beforeEach(() => {
  delete window.__EPOCHIX_VSCODE__;
  vi.restoreAllMocks();
});

describe('openIssue dispatch', () => {
  it('uses postMessage inside the VS Code webview, not window.open', () => {
    // A webview blocks navigation and discards window.open SILENTLY — the
    // button looks like it worked. That already shipped once for export.
    const post = vi.fn();
    window.__EPOCHIX_VSCODE__ = { postMessage: post };
    const open = vi.spyOn(window, 'open').mockImplementation(() => null);

    openIssue({ title: 't', labels: 'bug', body: 'b' });

    expect(post).toHaveBeenCalledTimes(1);
    expect(post.mock.calls[0][0].type).toBe('openExternal');
    expect(open).not.toHaveBeenCalled();
  });

  it('falls back to window.open in a plain browser', () => {
    const open = vi.spyOn(window, 'open').mockImplementation(() => null);
    openIssue({ title: 't', labels: 'bug', body: 'b' });
    expect(open).toHaveBeenCalledTimes(1);
  });
});

describe('reportFrame', () => {
  it('carries the reading being disputed', () => {
    const open = vi.spyOn(window, 'open').mockImplementation(() => null);
    reportFrame(FRAME, RUN, '0.5.88');

    const url = new URL(open.mock.calls[0][0]);
    const body = url.searchParams.get('body');
    expect(url.searchParams.get('title')).toContain('epoch 14');
    // Includes rather than equals: `bug` rides along because GitHub drops
    // unknown labels silently, and `correctness` had gone missing once.
    const labels = url.searchParams.get('labels').split(',');
    expect(labels).toContain('correctness');
    expect(labels).toContain('bug');
    expect(body).toContain('epoch        14');
    expect(body).toContain('val_accuracy');
    expect(body).toContain('0.5.88');
    expect(body).toContain(FRAME.narrative);
  });

  it('never includes the run name or a file path', () => {
    // A bug report must not be how someone's project name reaches a public
    // issue tracker.
    const open = vi.spyOn(window, 'open').mockImplementation(() => null);
    reportFrame(FRAME, RUN, '0.5.88');

    const body = new URL(open.mock.calls[0][0]).searchParams.get('body');
    expect(body).not.toContain('my-secret-project');
    expect(body).toMatch(/No run name, file path or log content is included/);
  });

  it('still files when the frame is missing pieces', () => {
    // A frame with no narrative is exactly when someone wants to complain.
    const open = vi.spyOn(window, 'open').mockImplementation(() => null);
    expect(() => reportFrame({}, null, undefined)).not.toThrow();
    expect(open).toHaveBeenCalled();
  });
});

describe('frameReportButton', () => {
  it('escapes the epoch into the aria-label', () => {
    const html = frameReportButton({ epoch: '1"><img src=x onerror=alert(1)>' });
    const host = document.createElement('div');
    host.innerHTML = html;
    expect(host.querySelectorAll('img')).toHaveLength(0);
  });
});
