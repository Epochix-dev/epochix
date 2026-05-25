/**
 * CompareView.js — multi-run comparison (TensorBoard/W&B style).
 *
 * Overlays several runs' metric curves on one chart with a colour-coded,
 * toggleable legend, a metric picker, and EMA smoothing. Data comes from
 * GET /api/compare?run_ids=a,b,c.
 */
import {
  allMetricKeys, emaSmooth, LOWER_IS_BETTER, metricLabel, seriesColor, seriesFromMetrics,
} from '../viz-util.js';

const _PREFERRED = ['val_accuracy', 'accuracy', 'val_loss', 'train_loss', 'mAP50'];

export class CompareView {
  /** @param {HTMLElement} container */
  constructor(container) {
    this._el = container;
    this._runs = [];          // [{run, frames, metrics}]
    this._metric = null;
    this._smoothing = 0.3;
    this._hidden = new Set(); // run ids toggled off
    this._canvas = null;
    this._ctx = null;
    this._resizeObs = null;
    this._cw = 800;
    this._ch = 360;
    this._color = new Map();  // run_id → colour
  }

  async load(runIds) {
    this._el.innerHTML = `<div class="cmp-loading">Loading runs…</div>`;
    let data;
    try {
      const r = await fetch(`/api/compare?run_ids=${encodeURIComponent(runIds.join(','))}`);
      if (!r.ok) throw new Error(`${r.status}`);
      data = await r.json();
    } catch (err) {
      this._el.innerHTML = `<div class="cmp-loading">Could not load runs: ${_esc(err.message)}</div>`;
      return;
    }
    this._runs = data.runs ?? [];
    if (this._runs.length === 0) {
      this._el.innerHTML = `<div class="cmp-loading">No runs to compare. Pick runs from the
        <a href="/">runs list</a>.</div>`;
      return;
    }
    this._runs.forEach((cr, i) => this._color.set(cr.run.id, seriesColor(i)));
    this._metric = this._defaultMetric();
    this._build();
    this._render();
  }

  unmount() {
    if (this._resizeObs) this._resizeObs.disconnect();
  }

  // ── internal ──────────────────────────────────────────────────────────────

  _defaultMetric() {
    const keys = allMetricKeys(this._runs.map((r) => r.metrics));
    for (const p of _PREFERRED) if (keys.includes(p)) return p;
    return keys[0] ?? null;
  }

  _build() {
    const keys = allMetricKeys(this._runs.map((r) => r.metrics));
    const opts = keys.map((k) =>
      `<option value="${_esc(k)}"${k === this._metric ? ' selected' : ''}>${_esc(metricLabel(k))}</option>`,
    ).join('');

    this._el.innerHTML = `
      <div class="cmp-controls">
        <label class="cmp-ctl">Metric
          <select id="cmp-metric">${opts}</select>
        </label>
        <label class="cmp-ctl">Smoothing
          <input id="cmp-smooth" type="range" min="0" max="0.95" step="0.05" value="${this._smoothing}">
        </label>
        <span class="cmp-count">${this._runs.length} runs</span>
      </div>
      <div class="cmp-chart-wrap"><canvas id="cmp-canvas"></canvas></div>
      <div class="cmp-legend" id="cmp-legend"></div>
    `;

    this._canvas = this._el.querySelector('#cmp-canvas');
    this._ctx = this._canvas.getContext('2d');

    this._el.querySelector('#cmp-metric').addEventListener('change', (e) => {
      this._metric = e.target.value;
      this._render();
    });
    this._el.querySelector('#cmp-smooth').addEventListener('input', (e) => {
      this._smoothing = parseFloat(e.target.value);
      this._render();
    });

    this._renderLegend();

    const wrap = this._el.querySelector('.cmp-chart-wrap');
    this._resizeObs = new ResizeObserver(() => this._resize());
    this._resizeObs.observe(wrap);
    this._resize();
  }

  _renderLegend() {
    const legend = this._el.querySelector('#cmp-legend');
    legend.innerHTML = this._runs.map((cr) => {
      const id = cr.run.id;
      const off = this._hidden.has(id);
      const name = cr.run.name ?? id.slice(0, 12);
      const grade = cr.run.final_grade ?? '—';
      return `
        <button class="cmp-leg-item${off ? ' is-off' : ''}" data-id="${_esc(id)}">
          <span class="cmp-leg-dot" style="background:${this._color.get(id)}"></span>
          <span class="cmp-leg-name">${_esc(name)}</span>
          <span class="cmp-leg-grade">${_esc(grade)}</span>
        </button>`;
    }).join('');
    legend.querySelectorAll('.cmp-leg-item').forEach((btn) => {
      btn.addEventListener('click', () => {
        const id = btn.dataset.id;
        if (this._hidden.has(id)) this._hidden.delete(id); else this._hidden.add(id);
        btn.classList.toggle('is-off');
        this._render();
      });
    });
  }

  _resize() {
    const wrap = this._el.querySelector('.cmp-chart-wrap');
    if (!wrap || !this._canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const w = wrap.clientWidth, h = wrap.clientHeight || 360;
    this._canvas.width = w * dpr;
    this._canvas.height = h * dpr;
    this._canvas.style.width = `${w}px`;
    this._canvas.style.height = `${h}px`;
    this._ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this._cw = w; this._ch = h;
    this._render();
  }

  _render() {
    if (!this._ctx) return;
    const ctx = this._ctx, w = this._cw, h = this._ch;
    ctx.clearRect(0, 0, w, h);

    // Gather visible series for the chosen metric.
    const series = [];
    for (const cr of this._runs) {
      if (this._hidden.has(cr.run.id)) continue;
      const raw = seriesFromMetrics(cr.metrics, this._metric);
      if (raw.length === 0) continue;
      const ys = emaSmooth(raw.map((p) => p.y), this._smoothing);
      series.push({
        id: cr.run.id,
        color: this._color.get(cr.run.id),
        pts: raw.map((p, i) => ({ x: p.x, y: ys[i] })),
      });
    }

    const ML = 52, MR = 16, MT = 16, MB = 30;
    const cw = w - ML - MR, ch = h - MT - MB;

    if (series.length === 0) {
      ctx.fillStyle = _css('--text-muted');
      ctx.font = '13px DM Sans, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(`No "${metricLabel(this._metric)}" data in the selected runs.`, w / 2, h / 2);
      return;
    }

    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    for (const s of series) for (const p of s.pts) {
      minX = Math.min(minX, p.x); maxX = Math.max(maxX, p.x);
      minY = Math.min(minY, p.y); maxY = Math.max(maxY, p.y);
    }
    if (maxX === minX) maxX = minX + 1;
    const pad = (maxY - minY) * 0.08 || 0.05;
    minY -= pad; maxY += pad;
    const xs = (x) => ML + ((x - minX) / (maxX - minX)) * cw;
    const ys = (y) => MT + (1 - (y - minY) / (maxY - minY)) * ch;

    // grid + axis labels
    ctx.strokeStyle = _css('--border-subtle');
    ctx.fillStyle = _css('--text-muted');
    ctx.lineWidth = 1;
    ctx.font = '10px DM Sans, sans-serif';
    for (let i = 0; i <= 4; i++) {
      const gy = MT + (i / 4) * ch;
      ctx.beginPath(); ctx.moveTo(ML, gy); ctx.lineTo(ML + cw, gy); ctx.stroke();
      const val = maxY - (i / 4) * (maxY - minY);
      ctx.textAlign = 'right';
      ctx.fillText(_fmt(val), ML - 6, gy + 3);
    }
    ctx.textAlign = 'center';
    for (let i = 0; i <= 5; i++) {
      const e = minX + (i / 5) * (maxX - minX);
      ctx.fillText(Math.round(e), xs(e), MT + ch + 14);
    }
    ctx.fillText('epoch', ML + cw / 2, MT + ch + 26);

    // lines
    for (const s of series) {
      ctx.beginPath();
      s.pts.forEach((p, i) => (i ? ctx.lineTo(xs(p.x), ys(p.y)) : ctx.moveTo(xs(p.x), ys(p.y))));
      ctx.strokeStyle = s.color;
      ctx.lineWidth = 2;
      ctx.stroke();
      const last = s.pts.at(-1);
      ctx.beginPath();
      ctx.arc(xs(last.x), ys(last.y), 3, 0, Math.PI * 2);
      ctx.fillStyle = s.color;
      ctx.fill();
    }

    // "lower is better" hint
    ctx.fillStyle = _css('--text-muted');
    ctx.font = '9px DM Sans, sans-serif';
    ctx.textAlign = 'left';
    ctx.fillText(
      LOWER_IS_BETTER.has(this._metric) ? '↓ lower is better' : '↑ higher is better',
      ML + 2, MT + 10,
    );
  }
}

function _css(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || '#888';
}
function _fmt(v) {
  if (!Number.isFinite(v)) return '';
  if (Math.abs(v) >= 100) return v.toFixed(0);
  if (Math.abs(v) >= 1) return v.toFixed(2);
  return v.toFixed(3);
}
function _esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
