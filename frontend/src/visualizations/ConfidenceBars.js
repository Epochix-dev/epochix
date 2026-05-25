/**
 * ConfidenceBars.js — horizontal metric value bars.
 *
 * Shows the most recent values for each canonical metric key.
 * Bars grow/shrink with CSS transitions.
 */

/** Keys where lower is better (losses, error rates) */
const LOWER_IS_BETTER = new Set([
  'train_loss', 'val_loss', 'loss', 'MAE', 'RMSE',
  'EER', 'epoch_time', 'eta', 'perplexity',
]);

export class ConfidenceBars {
  /** @param {HTMLElement} container */
  constructor(container) {
    this._el = container;
    this._unsub = null;
    this._rows = {};
  }

  /** @param {import('../store.js').AppState} store */
  mount(store) {
    this._unsub = store.subscribe((s) => {
      const f = s.currentFrame;
      if (!f) return;

      // Gather metric values from the frame
      const vals = _extractValues(s);
      this._render(vals);
    });
  }

  unmount() {
    if (this._unsub) this._unsub();
  }

  // ── internal ──────────────────────────────────────────────────────────────

  /** @param {Record<string, number>} vals */
  _render(vals) {
    const keys = Object.keys(vals).slice(0, 8); // max 8 rows
    if (keys.length === 0) return;

    // Add new rows
    for (const key of keys) {
      if (!this._rows[key]) {
        const row = document.createElement('div');
        row.className = 'conf-bar-row';
        row.innerHTML = `
          <span class="conf-bar-label" title="${key}">${_shortKey(key)}</span>
          <div class="conf-bar-track">
            <div class="conf-bar-fill" style="width:0%"></div>
          </div>
          <span class="conf-bar-value">—</span>
        `;
        this._el.appendChild(row);
        this._rows[key] = {
          fill:  row.querySelector('.conf-bar-fill'),
          value: row.querySelector('.conf-bar-value'),
        };
      }

      const v    = vals[key];
      const norm = _normalize(key, v, vals);
      const pct  = (norm * 100).toFixed(1);
      const col  = LOWER_IS_BETTER.has(key)
        ? `hsl(${200 + norm * 20}, 70%, 55%)`
        : `hsl(${140 + (1 - norm) * 80}, 70%, 55%)`;

      const { fill, value } = this._rows[key];
      fill.style.width  = `${pct}%`;
      fill.style.background = col;
      value.textContent = _fmt(v);
    }
  }
}

/** @param {import('../store.js').AppState} s */
function _extractValues(s) {
  // Use latest metric_events if available; else fall back to frame skills
  const vals = {};
  const metrics = s.metrics ?? [];
  if (metrics.length > 0) {
    // latest value per key
    for (const ev of metrics) {
      vals[ev.canonical_key] = ev.value;
    }
  } else if (s.currentFrame?.skill_dimensions) {
    Object.assign(vals, s.currentFrame.skill_dimensions);
    vals['confidence'] = s.currentFrame.confidence ?? 0;
  }
  return vals;
}

function _normalize(key, value, allVals) {
  if (LOWER_IS_BETTER.has(key)) {
    // Normalise: assume 0 is best, current value is worst seen
    const max = Math.max(...Object.values(allVals).filter(Number.isFinite), 1);
    return 1 - Math.min(1, value / max);
  }
  return Math.max(0, Math.min(1, value));
}

function _shortKey(key) {
  const map = {
    train_loss: 'train loss', val_loss: 'val loss',
    val_accuracy: 'val acc', accuracy: 'accuracy',
    mAP50: 'mAP50', mAP: 'mAP',
    MAE: 'MAE', RMSE: 'RMSE',
    EER: 'EER', perplexity: 'perplexity',
    bleu: 'BLEU', f1: 'F1',
    precision: 'precision', recall: 'recall',
  };
  return map[key] ?? key.replace(/_/g, ' ').slice(0, 12);
}

function _fmt(v) {
  if (!Number.isFinite(v)) return '—';
  if (Math.abs(v) >= 100) return v.toFixed(1);
  if (Math.abs(v) >= 1)   return v.toFixed(3);
  return v.toFixed(4);
}
