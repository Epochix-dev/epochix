/**
 * vscode-bridge.js — data path for the VS Code extension's *standalone* webview.
 *
 * When the extension has no Python sidecar it parses logs in-process
 * (StandaloneEngine) and pushes frames over `postMessage` instead of WebSocket.
 * The host injects `window.__MS_VSCODE__ = acquireVsCodeApi()` before this runs.
 *
 * The host protocol is camelCase (see model-story-vscode/src/webview/messages.ts);
 * the store speaks the server's snake_case frame shape — so we translate here.
 * Note: StandaloneEngine frames carry only the core story (no metric series or
 * detected architecture), so metric/architecture panels stay in their empty
 * state — that data only exists in sidecar mode.
 */
import { store, pushFrame, pushMilestone, pushWarning, scrubTo } from './store.js';

/** Map a host StoryFrameMsg (camelCase) → the store's frame shape (snake_case). */
function mapFrame(f) {
  return {
    seq: f.seq,
    epoch: f.epoch,
    progress: f.progress,
    phase: f.phase,
    grade: f.grade,
    primary_metric_value: f.primaryMetricValue,
    confidence: f.confidence,
    narrative: f.narrative,
    task_type: f.taskType,
  };
}

/**
 * Wire up the postMessage data path. Returns true if running inside the
 * VS Code webview (and the bridge took over), false otherwise.
 * @param {(theme: string) => void} applyTheme
 */
export function startVscodeBridge(applyTheme) {
  const vscode = window.__MS_VSCODE__;
  if (!vscode) return false;

  window.addEventListener('message', (ev) => {
    const msg = ev.data;
    if (!msg || !msg.type) return;

    switch (msg.type) {
      case 'init':
        if (msg.theme) applyTheme(msg.theme);
        store.set({
          run: null,
          live: !msg.hasSidecar,
          connected: true,
          metrics: [],
          architecture: null,
        });
        for (const f of msg.snapshot ?? []) pushFrame(mapFrame(f));
        for (const m of msg.milestones ?? []) pushMilestone(m);
        for (const w of msg.warnings ?? []) {
          if (w?.message) pushWarning(w.message);
        }
        break;

      case 'frame':
        if (msg.frame) pushFrame(mapFrame(msg.frame));
        break;

      case 'milestone':
        if (msg.milestone) pushMilestone(msg.milestone);
        break;

      case 'warning':
        if (msg.warning?.message) pushWarning(msg.warning.message);
        break;

      case 'complete': {
        const r = msg.run ?? {};
        store.set({
          run: {
            id: r.id,
            name: r.name,
            task_type: r.taskType,
            final_grade: r.finalGrade,
            story_summary: r.storySummary,
            finished_at: new Date().toISOString(),
          },
          live: false,
          connected: false,
        });
        break;
      }

      case 'themeChange':
        if (msg.theme) applyTheme(msg.theme);
        break;

      default:
        break;
    }
  });

  // Re-broadcast scrub requests from the UI back to the host engine.
  window.addEventListener('ms-scrub', (ev) => {
    const seq = ev.detail?.seq;
    if (typeof seq === 'number') {
      scrubTo(seq);
      vscode.postMessage({ type: 'scrub', seq });
    }
  });

  // Tell the host we're ready to receive the snapshot.
  vscode.postMessage({ type: 'ready' });
  return true;
}
