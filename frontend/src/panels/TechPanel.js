/**
 * TechPanel.js — Engineer panel with Chart.js loss/accuracy charts.
 *
 * Renders two line charts: one for loss metrics, one for accuracy/primary
 * metrics. Updates incrementally as new metric events arrive. TensorBoard-style
 * controls: EMA smoothing, log-scale loss, and an epoch/step x-axis toggle.
 */
import { emaSmooth, metricLabel } from '../viz-util.js';

export class TechPanel {
  /** @param {import('../store.js').AppState} store */
  constructor(store) {
    this._store      = store;
    this._lossChart  = null;
    this._accChart   = null;
    this._gapChart   = null;
    this._lrChart    = null;
    this._unsub      = null;
    this._chartJs    = null;
    this._smoothing  = 0.3;
    this._logScale   = false;
    this._xStep      = false;
  }

  async mount() {
    // Lazy-load Chart.js only when the panel is used
    try {
      const { Chart, registerables } = await import('chart.js');
      Chart.register(...registerables);
      this._chartJs = Chart;
    } catch {
      console.warn('[TechPanel] Chart.js not available');
      return;
    }

    this._buildCharts();
    this._wireControls();
    this._unsub = this._store.subscribe((s) => this._update(s));
    this._update(this._store.get());
  }

  _wireControls() {
    const smooth = document.getElementById('tech-smooth');
    const logsc  = document.getElementById('tech-logscale');
    const xstep  = document.getElementById('tech-xstep');
    smooth?.addEventListener('input', (e) => {
      this._smoothing = parseFloat(e.target.value);
      this._update(this._store.get());
    });
    logsc?.addEventListener('change', (e) => {
      this._logScale = e.target.checked;
      if (this._lossChart) {
        this._lossChart.options.scales.y.type = this._logScale ? 'logarithmic' : 'linear';
        this._lossChart.update('none');
      }
    });
    xstep?.addEventListener('change', (e) => {
      this._xStep = e.target.checked;
      this._update(this._store.get());
    });
  }

  unmount() {
    if (this._unsub) this._unsub();
    if (this._lossChart) this._lossChart.destroy();
    if (this._accChart)  this._accChart.destroy();
    if (this._gapChart)  this._gapChart.destroy();
    if (this._lrChart)   this._lrChart.destroy();
  }

  // ── internal ──────────────────────────────────────────────────────────────

  _buildCharts() {
    const Chart = this._chartJs;
    if (!Chart) return;

    const baseOpts = {
      responsive:          true,
      maintainAspectRatio: false,
      animation:           { duration: 400, easing: 'easeOutCubic' },
      interaction:         { mode: 'index', intersect: false },
      plugins: {
        legend: {
          align: 'end',
          labels: {
            color: this._cssVar('--text-secondary'),
            font: { size: 11 },
            usePointStyle: true,
            pointStyle: 'circle',
            boxWidth: 6,
            boxHeight: 6,
            padding: 14,
          },
        },
        tooltip: {
          backgroundColor: this._cssVar('--bg-elevated') || '#1f2842',
          borderColor: this._cssVar('--border-default') || 'rgba(255,255,255,0.12)',
          borderWidth: 1,
          titleColor: this._cssVar('--text-primary') || '#fff',
          bodyColor: this._cssVar('--text-secondary') || '#9aa3c4',
          padding: 10,
          cornerRadius: 8,
          usePointStyle: true,
          boxPadding: 4,
        },
      },
      scales: {
        x: {
          ticks: { color: this._cssVar('--text-muted'), font: { size: 10 } },
          grid:  { color: this._cssVar('--border-subtle'), drawTicks: false },
          border: { display: false },
          title: { display: true, text: 'Epoch', color: this._cssVar('--text-muted'), font: { size: 11 } },
        },
        y: {
          ticks: { color: this._cssVar('--text-muted'), font: { size: 10 } },
          grid:  { color: this._cssVar('--border-subtle'), drawTicks: false },
          border: { display: false },
        },
      },
    };

    const lossCanvas = document.getElementById('loss-chart');
    if (lossCanvas) {
      this._lossChart = new Chart(lossCanvas, {
        type: 'line',
        data: { labels: [], datasets: [] },
        options: {
          ...baseOpts,
          plugins: {
            ...baseOpts.plugins,
            legend: { ...baseOpts.plugins.legend },
            title: {
              display: true,
              text: 'Loss',
              color: this._cssVar('--text-secondary'),
              font: { size: 12 },
            },
          },
        },
      });
    }

    const accCanvas = document.getElementById('accuracy-chart');
    if (accCanvas) {
      this._accChart = new Chart(accCanvas, {
        type: 'line',
        data: { labels: [], datasets: [] },
        options: {
          ...baseOpts,
          plugins: {
            ...baseOpts.plugins,
            title: {
              display: true,
              text: 'Accuracy',
              color: this._cssVar('--text-secondary'),
              font: { size: 12 },
            },
          },
        },
      });
    }

    const lrCanvas = document.getElementById('lr-chart');
    if (lrCanvas) {
      // LR is plotted on a log scale by default — schedules typically span
      // orders of magnitude (1e-3 → 1e-5 with cosine decay etc.).
      this._lrChart = new Chart(lrCanvas, {
        type: 'line',
        data: { labels: [], datasets: [] },
        options: {
          ...baseOpts,
          plugins: {
            ...baseOpts.plugins,
            title: {
              display: true,
              text: 'Learning rate (log)',
              color: this._cssVar('--text-secondary'),
              font: { size: 12 },
            },
          },
          scales: {
            ...baseOpts.scales,
            y: { ...baseOpts.scales.y, type: 'logarithmic' },
          },
        },
      });
    }

    const gapCanvas = document.getElementById('gap-chart');
    if (gapCanvas) {
      this._gapChart = new Chart(gapCanvas, {
        type: 'line',
        data: { labels: [], datasets: [] },
        options: {
          ...baseOpts,
          plugins: {
            ...baseOpts.plugins,
            title: {
              display: true,
              text: 'Overfitting gap (val − train)',
              color: this._cssVar('--text-secondary'),
              font: { size: 12 },
            },
          },
        },
      });
    }
  }

  /** @param {import('../store.js').AppState} s */
  _update(s) {
    const frames = s.frames;
    if (frames.length === 0) return;

    // X axis: epoch (default) or step.
    const labels = this._xStep
      ? frames.map((f, i) => f.step ?? f.epoch ?? i)
      : frames.map((f, i) => f.epoch ?? i);

    let trainLoss = frames.map((f) => _findMetric(s.metrics, f, 'train_loss'));
    let valLoss   = frames.map((f) => _findMetric(s.metrics, f, 'val_loss'));
    let   trainAcc  = frames.map((f) => _findMetric(s.metrics, f, 'accuracy'));
    let   valAcc    = frames.map((f) => _findMetric(s.metrics, f, 'val_accuracy'));

    // Auxiliary loss components (YOLO/multi-task): only surfaced if present.
    const boxLoss = frames.map((f) => _findMetric(s.metrics, f, 'box_loss'));
    const clsLoss = frames.map((f) => _findMetric(s.metrics, f, 'cls_loss'));
    const dflLoss = frames.map((f) => _findMetric(s.metrics, f, 'dfl_loss'));
    // Detection-specific quality metrics — used as accuracy fallback below.
    const map50    = frames.map((f) => _findMetric(s.metrics, f, 'mAP50'));
    const map50_95 = frames.map((f) => _findMetric(s.metrics, f, 'mAP'));
    const precision = frames.map((f) => _findMetric(s.metrics, f, 'precision'));
    const recall    = frames.map((f) => _findMetric(s.metrics, f, 'recall'));
    // Learning-rate schedule.
    const lr = frames.map((f) => _findMetric(s.metrics, f, 'lr'));

    // Detection runs have no train_loss/val_loss but DO have box+cls+dfl.
    // Fall back to the aux-loss sum as a sensible "total training loss"
    // proxy so the loss chart isn't empty.
    const hasClassicLoss =
      trainLoss.some((v) => v != null) || valLoss.some((v) => v != null);
    if (!hasClassicLoss && boxLoss.some((v) => v != null)) {
      trainLoss = frames.map((_, i) => {
        const parts = [boxLoss[i], clsLoss[i], dflLoss[i]].filter((v) => v != null);
        return parts.length ? parts.reduce((a, b) => a + b, 0) : null;
      });
      // No separate val loss in detection logs — leave valLoss as null array.
    }

    // Accuracy fallbacks for detection/regression/etc:
    //  1. explicit accuracy series
    //  2. mAP50 + mAP50-95 (detection — labelled honestly, not as "val acc")
    //  3. the frame's primary metric value (universal last-ditch)
    let accLabels = { train: 'train acc', val: 'val acc' };
    const hasAcc = trainAcc.some((v) => v != null) || valAcc.some((v) => v != null);
    if (!hasAcc) {
      if (map50.some((v) => v != null)) {
        valAcc    = map50;
        trainAcc  = map50_95;
        accLabels = { train: 'mAP50-95', val: 'mAP50' };
      } else {
        valAcc   = frames.map((f) => f.primary_metric_value ?? null);
        trainAcc = frames.map(() => null);
        accLabels = { train: 'train acc', val: 'primary metric' };
      }
    }

    // Overfitting gap — fall back to (precision − recall) when train/val loss
    // are absent; it's the closest detection-domain analogue.
    let gap = frames.map((_, i) =>
      (valLoss[i] != null && trainLoss[i] != null) ? valLoss[i] - trainLoss[i] : null);
    let gapLabel = 'val − train loss';
    if (!gap.some((v) => v != null) && precision.some((v) => v != null)) {
      gap = frames.map((_, i) =>
        (precision[i] != null && recall[i] != null) ? precision[i] - recall[i] : null);
      gapLabel = 'precision − recall';
    }

    const sm = (arr) => emaSmooth(arr, this._smoothing);

    // Best-epoch markers: single-point datasets that highlight the optimum on
    // the curve itself (researchers shouldn't have to look at the table).
    const smValLoss = sm(valLoss);
    const smValAcc  = sm(valAcc);
    const bestValLossMarker = _bestMarker(smValLoss, 'min');
    const bestValAccMarker  = _bestMarker(smValAcc,  'max');

    // Cool family for quality metrics, warm family for losses — matches the
    // dashboard's purple→cyan / pink→orange gradient system. Multi-loss
    // components stack onto the loss chart only when actually reported.
    const lossSeries = [
      { label: 'train loss', data: sm(trainLoss), color: '#fb923c' },
      { label: 'val loss',   data: smValLoss,     color: '#f472b6' },
      { label: 'box',        data: sm(boxLoss),   color: '#a78bfa', dashed: true },
      { label: 'cls',        data: sm(clsLoss),   color: '#22d3ee', dashed: true },
      { label: 'dfl',        data: sm(dflLoss),   color: '#34d399', dashed: true },
    ].filter((d) => d.data.some((v) => v != null));
    this._setChartData(this._lossChart, labels, lossSeries, [
      { label: 'best val ★', data: bestValLossMarker, color: '#f472b6', marker: true },
    ]);

    this._setChartData(this._accChart, labels, [
      { label: accLabels.train, data: sm(trainAcc), color: '#7c6dff' },
      { label: accLabels.val,   data: smValAcc,     color: '#22d3ee' },
    ].filter((d) => d.data.some((v) => v != null)), [
      { label: `best ${accLabels.val} ★`, data: bestValAccMarker, color: '#22d3ee', marker: true },
    ]);

    this._setChartData(this._gapChart, labels, [
      { label: gapLabel, data: sm(gap), color: '#f87171' },
    ]);

    // Learning-rate schedule — never smoothed (it's a deterministic schedule),
    // hide chart when no `lr` events were logged.
    const hasLr = lr.some((v) => v != null && v > 0);
    if (this._lrChart) {
      this._lrChart.canvas.parentElement.style.display = hasLr ? '' : 'none';
      if (hasLr) {
        this._setChartData(this._lrChart, labels, [
          { label: 'lr', data: lr, color: '#fbbf24' },
        ]);
      }
    }

    this._renderStats(s);
  }

  /** Compact per-metric stats table: latest · best · @epoch. */
  _renderStats(s) {
    const host = document.getElementById('tech-stats');
    if (!host) return;
    const lowerBetter = new Set(['train_loss', 'val_loss', 'loss', 'MAE', 'RMSE', 'perplexity']);
    const byKey = new Map();
    for (const m of s.metrics ?? []) {
      if (!Number.isFinite(m.value)) continue;
      let arr = byKey.get(m.canonical_key);
      if (!arr) { arr = []; byKey.set(m.canonical_key, arr); }
      arr.push({ epoch: m.epoch ?? 0, value: m.value });
    }
    if (byKey.size === 0) { host.innerHTML = ''; return; }

    const rows = [...byKey.entries()].map(([key, pts]) => {
      const latest = pts[pts.length - 1].value;
      const lower = lowerBetter.has(key);
      const best = pts.reduce((b, p) => (lower ? p.value < b.value : p.value > b.value) ? p : b, pts[0]);
      return `
        <tr>
          <td class="ts-key">${_esc(metricLabel(key))}</td>
          <td>${_num(latest)}</td>
          <td class="ts-best">${_num(best.value)}</td>
          <td class="ts-ep">ep ${best.epoch}</td>
        </tr>`;
    }).join('');

    host.innerHTML = `
      <table class="ts-table">
        <thead><tr><th>metric</th><th>latest</th><th>best</th><th>@</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>`;
  }

  _setChartData(chart, labels, series, markers = []) {
    if (!chart) return;
    chart.data.labels = labels;
    const lineDatasets = series.map(({ label, data, color, dashed }) => ({
      label,
      data,
      borderColor:          color,
      backgroundColor:      _gradientFill(color),
      borderWidth:          2,
      borderDash:           dashed ? [4, 4] : [],
      pointRadius:          0,
      pointHoverRadius:     4,
      pointBackgroundColor: color,
      pointBorderColor:     '#fff',
      pointBorderWidth:     1,
      fill:                 !dashed,   // dashed aux series don't get area fill
      tension:              0.4,
      spanGaps:             true,
    }));
    // Best-epoch markers: a star at the single best-value point on the curve.
    const markerDatasets = markers.map(({ label, data, color }) => ({
      label,
      data,
      borderColor:          color,
      backgroundColor:      color,
      pointStyle:           'star',
      pointRadius:          10,
      pointHoverRadius:     12,
      pointBorderColor:     '#fff',
      pointBorderWidth:     1.5,
      showLine:             false,
      fill:                 false,
      spanGaps:             true,
    }));
    chart.data.datasets = [...lineDatasets, ...markerDatasets];
    chart.update('none');
  }

  _cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || '#888';
  }
}

/**
 * Scriptable Chart.js backgroundColor: a vertical gradient from the line colour
 * (translucent at top) to transparent at the bottom — the "area chart" look
 * from the reference dashboards.
 * @param {string} hex
 */
function _gradientFill(hex) {
  return (context) => {
    const chart = context.chart;
    const { ctx, chartArea } = chart;
    if (!chartArea) return _hexA(hex, 0.12);   // before first layout
    const g = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
    g.addColorStop(0, _hexA(hex, 0.38));
    g.addColorStop(1, _hexA(hex, 0.0));
    return g;
  };
}

function _hexA(hex, a) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${a})`;
}

function _num(v) {
  if (!Number.isFinite(v)) return '—';
  if (Math.abs(v) >= 100) return v.toFixed(1);
  if (Math.abs(v) >= 1) return v.toFixed(3);
  return v.toFixed(4);
}

function _esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/**
 * Look up a metric value at a given frame's epoch from metric events.
 * Falls back to null.
 * @param {object[]} metrics
 * @param {object} frame
 * @param {string} key
 */
/**
 * Single-point dataset that highlights the argmin/argmax of a series so the
 * best checkpoint is visible on the curve itself (not just in the table).
 * @param {Array<number|null>} arr
 * @param {'min'|'max'} mode
 */
function _bestMarker(arr, mode) {
  let bestI = -1;
  let bestV = mode === 'min' ? Infinity : -Infinity;
  for (let i = 0; i < arr.length; i++) {
    const v = arr[i];
    if (v == null || !Number.isFinite(v)) continue;
    if (mode === 'min' ? v < bestV : v > bestV) { bestV = v; bestI = i; }
  }
  if (bestI < 0) return arr.map(() => null);
  return arr.map((_, i) => (i === bestI ? bestV : null));
}

function _findMetric(metrics, frame, key) {
  if (!metrics?.length) return null;
  // Find the metric event closest to this frame's epoch
  const epoch = frame.epoch;
  if (epoch == null) return null;
  let best = null;
  let bestDist = Infinity;
  for (const m of metrics) {
    if (m.canonical_key !== key) continue;
    const d = Math.abs((m.epoch ?? 0) - epoch);
    if (d < bestDist) { bestDist = d; best = m.value; }
  }
  return best;
}
