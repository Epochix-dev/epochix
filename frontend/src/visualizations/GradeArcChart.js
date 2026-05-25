/**
 * GradeArcChart.js — the central learning-curve visualization.
 *
 * Shows ALL training epochs in one chart:
 *  • Blue line  = val_accuracy (or primary metric) over epochs
 *  • Red line   = val_loss over epochs
 *  • Coloured background bands = phase zones (awakening / learning / ...)
 *  • Dashed horizontal lines  = grade thresholds (A+, A, B+, …)
 *  • Animated dot             = current epoch position
 *
 * This makes the "story" legible as a graph: you see exactly when the model
 * crossed from B to B+, when loss plateaued, when the phase changed.
 */

const PHASE_BG = {
  awakening:     'rgba(167,139,250,0.10)',
  learning:      'rgba( 96,165,250,0.10)',
  understanding: 'rgba( 52,211,153,0.10)',
  mastering:     'rgba(251,191, 36,0.10)',
  polishing:     'rgba(244,114,182,0.10)',
};

// Classification grade thresholds (higher = better)
const GRADE_LINES = [
  { grade: 'A+', v: 0.97, color: '#34d399' },
  { grade: 'A',  v: 0.93, color: '#60a5fa' },
  { grade: 'A-', v: 0.87, color: '#818cf8' },
  { grade: 'B+', v: 0.82, color: '#a78bfa' },
  { grade: 'B',  v: 0.76, color: '#c084fc' },
  { grade: 'B-', v: 0.70, color: '#e879f9' },
  { grade: 'C+', v: 0.63, color: '#fb923c' },
  { grade: 'C',  v: 0.55, color: '#f97316' },
];

export class GradeArcChart {
  /** @param {HTMLCanvasElement} canvas */
  constructor(canvas) {
    this._canvas = canvas;
    this._ctx    = canvas.getContext('2d');
    this._store  = null;
    this._unsub  = null;
    this._raf    = null;
    this._t      = 0;
    this._frames = [];
    this._metrics = [];
    this._resizeObs = null;
    this._cw = 800;
    this._ch = 180;

    // Interactive hover state
    this._geom     = null;   // {ML,MT,cw,ch,minEpoch,maxEpoch,xScale,yScale,accPts}
    this._hoverIdx = null;
    this._tooltip  = null;
    this._onMove   = null;
    this._onLeave  = null;
  }

  mount(store) {
    this._store = store;
    this._unsub = store.subscribe((s) => {
      this._frames  = s.frames  ?? [];
      this._metrics = s.metrics ?? [];
      this._draw();
    });
    this._resizeObs = new ResizeObserver(() => this._resize());
    this._resizeObs.observe(this._canvas.parentElement);
    this._resize();

    // ── Hover tooltip + crosshair ─────────────────────────────────────────
    const wrap = this._canvas.parentElement;
    if (wrap) {
      const tip = document.createElement('div');
      tip.className = 'arc-tooltip';
      tip.style.display = 'none';
      wrap.appendChild(tip);
      this._tooltip = tip;

      this._onMove = (e) => {
        const rect = this._canvas.getBoundingClientRect();
        this._handleHover(e.clientX - rect.left, e.clientY - rect.top);
      };
      this._onLeave = () => {
        this._hoverIdx = null;
        if (this._tooltip) this._tooltip.style.display = 'none';
      };
      this._canvas.addEventListener('mousemove', this._onMove);
      this._canvas.addEventListener('mouseleave', this._onLeave);
    }

    // Pulse loop for the "current position" dot
    const loop = () => {
      this._t += 0.04;
      this._draw();
      this._raf = requestAnimationFrame(loop);
    };
    this._raf = requestAnimationFrame(loop);
  }

  unmount() {
    if (this._unsub) this._unsub();
    if (this._resizeObs) this._resizeObs.disconnect();
    cancelAnimationFrame(this._raf);
    if (this._onMove)  this._canvas.removeEventListener('mousemove', this._onMove);
    if (this._onLeave) this._canvas.removeEventListener('mouseleave', this._onLeave);
    if (this._tooltip) this._tooltip.remove();
  }

  /** Map a cursor x/y to the nearest epoch and update the tooltip. */
  _handleHover(px, py) {
    const g = this._geom;
    if (!g || !g.accPts.length) return;
    // nearest epoch dot by x
    let idx = 0, bestDist = Infinity;
    for (let i = 0; i < g.accPts.length; i++) {
      const d = Math.abs(g.accPts[i].x - px);
      if (d < bestDist) { bestDist = d; idx = i; }
    }
    this._hoverIdx = idx;

    const f      = this._frames[idx];
    const epoch  = f?.epoch ?? idx;
    const acc    = f?.primary_metric_value;
    const grade  = f?.grade;
    const valLoss = _metricAt(this._metrics, 'val_loss', epoch)
                 ?? _metricAt(this._metrics, 'train_loss', epoch);
    const lossKey = this._metrics.some((m) => m.canonical_key === 'val_loss') ? 'val loss' : 'train loss';

    const rows = [
      `<div class="arc-tip-epoch">Epoch ${_esc(String(epoch))}</div>`,
      acc != null   ? `<div><span class="arc-tip-k">accuracy</span><span class="arc-tip-v">${(acc * 100).toFixed(1)}%</span></div>` : '',
      valLoss != null ? `<div><span class="arc-tip-k">${lossKey}</span><span class="arc-tip-v">${valLoss.toFixed(3)}</span></div>` : '',
      grade         ? `<div><span class="arc-tip-k">grade</span><span class="arc-tip-v">${_esc(grade)}</span></div>` : '',
    ].filter(Boolean).join('');

    if (this._tooltip) {
      this._tooltip.innerHTML = rows;
      this._tooltip.style.display = 'block';
      // position near cursor, clamped within the wrap
      const wrapW = this._cw;
      const tx = Math.min(px + 14, wrapW - 130);
      this._tooltip.style.left = `${Math.max(4, tx)}px`;
      this._tooltip.style.top  = `${Math.max(4, py - 10)}px`;
    }
  }

  // ── internal ──────────────────────────────────────────────────────────────

  _resize() {
    const parent = this._canvas.parentElement;
    if (!parent) return;
    const dpr = window.devicePixelRatio || 1;
    const w   = parent.clientWidth;
    const h   = parent.clientHeight || 180;
    this._canvas.width  = w * dpr;
    this._canvas.height = h * dpr;
    this._canvas.style.width  = `${w}px`;
    this._canvas.style.height = `${h}px`;
    this._ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this._cw = w;
    this._ch = h;
    this._draw();
  }

  _draw() {
    const ctx    = this._ctx;
    const w      = this._cw;
    const h      = this._ch;
    const frames = this._frames;

    ctx.clearRect(0, 0, w, h);

    if (frames.length === 0) {
      ctx.fillStyle = 'rgba(148,163,184,0.3)';
      ctx.font = '13px DM Sans, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('Waiting for training data…', w / 2, h / 2);
      return;
    }

    // Layout margins
    const ML = 44, MR = 20, MT = 16, MB = 28;
    const cw = w - ML - MR;
    const ch = h - MT - MB;

    // X axis: epoch range
    const epochs  = frames.map((f) => f.epoch ?? 0);
    const minEpoch = Math.min(...epochs);
    const maxEpoch = Math.max(...epochs);
    const xScale = (e) => ML + ((e - minEpoch) / Math.max(1, maxEpoch - minEpoch)) * cw;

    // Y axis: 0..1 (val_accuracy / primary metric)
    const yScale = (v) => MT + (1 - Math.max(0, Math.min(1, v))) * ch;

    // ── Phase background bands ─────────────────────────────────────────────
    let prevPhase = null, prevX = ML;
    for (let i = 0; i < frames.length; i++) {
      const f = frames[i];
      const x = xScale(f.epoch ?? i);
      if (f.phase !== prevPhase) {
        if (prevPhase && PHASE_BG[prevPhase]) {
          ctx.fillStyle = PHASE_BG[prevPhase];
          ctx.fillRect(prevX, MT, x - prevX, ch);
        }
        prevPhase = f.phase;
        prevX = x;
      }
    }
    // Fill final phase band
    if (prevPhase && PHASE_BG[prevPhase]) {
      ctx.fillStyle = PHASE_BG[prevPhase];
      ctx.fillRect(prevX, MT, ML + cw - prevX, ch);
    }

    // ── Grade threshold lines ──────────────────────────────────────────────
    ctx.font         = '9px DM Sans, sans-serif';
    ctx.textAlign    = 'left';
    for (const { grade, v, color } of GRADE_LINES) {
      const y = yScale(v);
      if (y < MT || y > MT + ch) continue;
      ctx.beginPath();
      ctx.setLineDash([3, 6]);
      ctx.moveTo(ML, y);
      ctx.lineTo(ML + cw, y);
      ctx.strokeStyle = color + '66';   // slightly more visible
      ctx.lineWidth   = 1;
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = color + 'cc';     // brighter labels
      ctx.fillText(grade, 2, y + 3.5);
    }

    // ── Axes ──────────────────────────────────────────────────────────────
    ctx.beginPath();
    ctx.moveTo(ML, MT);
    ctx.lineTo(ML, MT + ch);
    ctx.lineTo(ML + cw, MT + ch);
    ctx.strokeStyle = 'rgba(148,163,184,0.2)';
    ctx.lineWidth   = 1;
    ctx.setLineDash([]);
    ctx.stroke();

    // Epoch tick labels
    ctx.font      = '9px DM Sans, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillStyle = 'rgba(148,163,184,0.6)';
    const tickCount = Math.min(frames.length, 10);
    for (let i = 0; i <= tickCount; i++) {
      const e = minEpoch + (i / tickCount) * (maxEpoch - minEpoch);
      const x = xScale(e);
      ctx.fillText(Math.round(e), x, MT + ch + 14);
    }
    ctx.fillText('epoch', ML + cw / 2, MT + ch + 24);

    // ── Loss line (val_loss preferred, fall back to train_loss) ──────────
    // Normalise: loss is 0..∞, invert to 0..1 so it tracks quality visually.
    let lossData = _buildMetricSeries(this._metrics, frames, 'val_loss', xScale);
    if (lossData.length < 2)
      lossData = _buildMetricSeries(this._metrics, frames, 'train_loss', xScale);
    const lossLabel = this._metrics.some((m) => m.canonical_key === 'val_loss')
      ? 'val loss' : 'train loss (↓ better)';
    if (lossData.length >= 2) {
      const maxL = Math.max(...lossData.map((p) => p.v), 0.001);
      // Invert so decreasing loss → rising line (matches "quality" direction)
      const normLoss = lossData.map((p) => ({ x: p.x, v: 1 - Math.min(1, p.v / maxL) }));
      ctx.beginPath();
      ctx.moveTo(normLoss[0].x, yScale(normLoss[0].v));
      for (const pt of normLoss.slice(1)) ctx.lineTo(pt.x, yScale(pt.v));
      ctx.strokeStyle = 'rgba(239,68,68,0.55)';
      ctx.lineWidth   = 1.5;
      ctx.setLineDash([4, 3]);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // ── Primary metric line (val_accuracy) — main thick line ────────────
    const accPts = frames.map((f, i) => ({
      x: xScale(f.epoch ?? i),
      v: f.primary_metric_value ?? 0,
    }));

    // Stash geometry for hover interaction
    this._geom = { ML, MT, cw, ch, minEpoch, maxEpoch, xScale, yScale, accPts };

    if (accPts.length >= 2) {
      // Fill under the curve
      ctx.beginPath();
      ctx.moveTo(accPts[0].x, yScale(0));
      for (const pt of accPts) ctx.lineTo(pt.x, yScale(pt.v));
      ctx.lineTo(accPts.at(-1).x, yScale(0));
      ctx.closePath();
      ctx.fillStyle = 'rgba(96,165,250,0.08)';
      ctx.fill();

      // Stroke
      ctx.beginPath();
      ctx.moveTo(accPts[0].x, yScale(accPts[0].v));
      for (const pt of accPts.slice(1)) ctx.lineTo(pt.x, yScale(pt.v));
      ctx.strokeStyle = '#60a5fa';
      ctx.lineWidth   = 2;
      ctx.stroke();
    }

    // ── Epoch dots on the primary metric line ────────────────────────────
    for (const pt of accPts) {
      ctx.beginPath();
      ctx.arc(pt.x, yScale(pt.v), 3, 0, Math.PI * 2);
      ctx.fillStyle = '#60a5fa';
      ctx.fill();
    }

    // ── Animated "current position" pulse ────────────────────────────────
    const last = accPts.at(-1);
    if (last) {
      const pulse = 0.5 + 0.5 * Math.sin(this._t);
      const pr    = 5 + pulse * 4;
      ctx.beginPath();
      ctx.arc(last.x, yScale(last.v), pr, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(96,165,250,${0.15 * pulse})`;
      ctx.fill();
      ctx.beginPath();
      ctx.arc(last.x, yScale(last.v), 4, 0, Math.PI * 2);
      ctx.fillStyle = '#60a5fa';
      ctx.fill();
    }

    // ── Hover crosshair + highlighted point ──────────────────────────────
    if (this._hoverIdx != null && accPts[this._hoverIdx]) {
      const hp = accPts[this._hoverIdx];
      ctx.beginPath();
      ctx.setLineDash([2, 3]);
      ctx.moveTo(hp.x, MT);
      ctx.lineTo(hp.x, MT + ch);
      ctx.strokeStyle = 'rgba(226,232,240,0.35)';
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.setLineDash([]);
      // emphasised marker
      ctx.beginPath();
      ctx.arc(hp.x, yScale(hp.v), 5, 0, Math.PI * 2);
      ctx.fillStyle = '#fff';
      ctx.fill();
      ctx.beginPath();
      ctx.arc(hp.x, yScale(hp.v), 3, 0, Math.PI * 2);
      ctx.fillStyle = '#60a5fa';
      ctx.fill();
    }

    // ── Legend ────────────────────────────────────────────────────────────
    const lx = ML + cw - 130;
    ctx.font = '10px DM Sans, sans-serif';
    ctx.textAlign = 'left';

    ctx.beginPath();
    ctx.moveTo(lx, MT + 10); ctx.lineTo(lx + 18, MT + 10);
    ctx.strokeStyle = '#60a5fa'; ctx.lineWidth = 2; ctx.setLineDash([]); ctx.stroke();
    ctx.fillStyle = 'rgba(148,163,184,0.8)';
    ctx.fillText('val accuracy', lx + 22, MT + 14);

    if (lossData.length >= 2) {
      ctx.beginPath();
      ctx.moveTo(lx, MT + 24); ctx.lineTo(lx + 18, MT + 24);
      ctx.strokeStyle = 'rgba(239,68,68,0.6)'; ctx.lineWidth = 1.5;
      ctx.setLineDash([4, 3]); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = 'rgba(148,163,184,0.8)';
      ctx.fillText(lossLabel, lx + 22, MT + 28);
    }
  }
}

/** Nearest metric value for a canonical key at a given epoch. */
function _metricAt(metrics, key, epoch) {
  if (!metrics?.length) return null;
  let best = null, bestDist = Infinity;
  for (const m of metrics) {
    if (m.canonical_key !== key) continue;
    const d = Math.abs((m.epoch ?? 0) - epoch);
    if (d < bestDist) { bestDist = d; best = m.value; }
  }
  return best;
}

function _esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/** Pull metric values per-epoch from the raw events list. */
function _buildMetricSeries(metrics, frames, key, xScale) {
  if (!metrics?.length) return [];
  return frames.map((f, i) => {
    const epoch = f.epoch ?? i;
    let best = null, bestDist = Infinity;
    for (const m of metrics) {
      if (m.canonical_key !== key) continue;
      const d = Math.abs((m.epoch ?? 0) - epoch);
      if (d < bestDist) { bestDist = d; best = m.value; }
    }
    return best !== null ? { x: xScale(epoch), v: best } : null;
  }).filter(Boolean);
}
