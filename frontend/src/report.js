/**
 * Filing a bug from inside the dashboard.
 *
 * One place, because the dashboard runs in three environments with different
 * rules and each one needs a different way out:
 *
 *   - a real browser        → window.open
 *   - the VS Code webview   → postMessage to the extension host
 *   - the webview's iframe  → postMessage to the parent, which forwards
 *
 * A webview blocks navigation, so `window.open` there is silently discarded —
 * the button looks like it worked and nothing happens. That failure has
 * already shipped once for the export button.
 */
import { escapeHtml } from './escape.js';

const ISSUE_URL = 'https://github.com/Epochix-dev/epochix/issues/new';

/** Send the user to a prefilled issue, whichever surface we are running in. */
export function openIssue({ title = '', labels = '', body = '' } = {}) {
  const url =
    `${ISSUE_URL}?labels=${encodeURIComponent(labels)}` +
    `&title=${encodeURIComponent(title)}` +
    `&body=${encodeURIComponent(body)}`;

  if (window.__EPOCHIX_VSCODE__) {
    window.__EPOCHIX_VSCODE__.postMessage({ type: 'openExternal', url });
  } else if (window.parent !== window) {
    window.parent.postMessage({ type: 'openExternal', url }, '*');
  } else {
    window.open(url, '_blank', 'noopener');
  }
  return url;
}

/**
 * Report one specific reading as wrong.
 *
 * The whole-dashboard report button asks "something looks off"; this asks
 * "THIS number is wrong", and carries the epoch, the value and the sentence
 * that was written about it. A wrong number is this product's characteristic
 * failure — it renders perfectly and states something false — so the report
 * has to pin down which reading, not just which run.
 *
 * Carries no run name, file path or log content: a bug report should not be
 * how someone's project name reaches a public issue tracker.
 */
export function reportFrame(frame, run, version = '(unknown)') {
  const body = [
    '### Which reading looks wrong?',
    '',
    `> ${frame?.narrative ?? '(no narrative on this frame)'}`,
    '',
    '### What should it have said instead?',
    '',
    '',
    '---',
    '```',
    `epochix      ${version}`,
    `surface      dashboard (single frame)`,
    `epoch        ${frame?.epoch ?? '(none)'}`,
    `metric       ${frame?.primary_metric ?? run?.primary_metric ?? '(unknown)'}`,
    `value        ${frame?.primary_metric_value ?? '(none)'}`,
    `grade        ${frame?.grade ?? '(none)'}`,
    `phase        ${frame?.phase ?? '(none)'}`,
    `task         ${run?.task_type ?? '(unknown)'}`,
    `browser      ${navigator.userAgent}`,
    '```',
    '',
    '_No run name, file path or log content is included._',
  ].join('\n');

  return openIssue({
    title: `Wrong reading at epoch ${frame?.epoch ?? '?'}: `,
    labels: REPORT_LABELS,
    body,
  });
}

/** Labels every dashboard report carries.
 *
 * `bug` first and deliberately: GitHub silently DROPS unknown labels from an
 * `/issues/new?labels=` link, and this asked for `correctness` alone — which
 * did not exist in the repo. Every dashboard report therefore arrived with no
 * label at all and no error anywhere, while the extension's own report command
 * (which asks for `bug`) labelled fine. Issue #35 came in unlabelled for
 * exactly this reason.
 *
 * `bug` is a label GitHub creates with every repository, so pairing them keeps
 * a report triageable even if `correctness` is renamed or deleted again.
 */
export const REPORT_LABELS = 'bug,correctness';

/** The control itself — small, quiet, and next to the sentence it disputes. */
export function frameReportButton(frame) {
  const epoch = escapeHtml(String(frame?.epoch ?? '?'));
  return (
    `<button class="frame-report" type="button" ` +
    `title="Report this reading as wrong" ` +
    `aria-label="Report the reading at epoch ${epoch} as wrong">` +
    `this looks wrong</button>`
  );
}
