/**
 * TechPanel.js — Engineer panel with Chart.js loss/accuracy charts.
 *
 * Renders two line charts: one for loss metrics, one for accuracy/primary
 * metrics. Updates incrementally as new metric events arrive.
 */

export class TechPanel {
  /** @param {import('../store.js').AppState} store */
  constructor(store) {
    this._store      = store;
    this._lossChart  = null;
    this._accChart   = null;
    this._unsub      = null;
    this._chartJs    = null;
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
    this._unsub = this._store.subscribe((s) => this._update(s));
    this._update(this._store.get());
  }

  unmount() {
    if (this._unsub) this._unsub();
    if (this._lossChart) this._lossChart.destroy();
    if (this._accChart)  this._accChart.destroy();
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
              text: 'Primary Metric',
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

    // Build series from frames
    const labels     = frames.map((f) => f.epoch ?? frames.indexOf(f));
    const trainLoss  = frames.map((f) => _findMetric(s.metrics, f, 'train_loss'));
    const valLoss    = frames.map((f) => _findMetric(s.metrics, f, 'val_loss'));
    const primary    = frames.map((f) => f.primary_metric_value ?? null);
    const confidence = frames.map((f) => f.confidence ?? null);

    // Cool family for quality metrics, warm family for losses — matches the
    // dashboard's purple→cyan / pink→orange gradient system.
    this._setChartData(this._lossChart, labels, [
      { label: 'train loss', data: trainLoss,  color: '#fb923c' },
      { label: 'val loss',   data: valLoss,    color: '#f472b6' },
    ]);

    this._setChartData(this._accChart, labels, [
      { label: 'primary metric', data: primary,    color: '#7c6dff' },
      { label: 'confidence',     data: confidence, color: '#22d3ee' },
    ]);
  }

  _setChartData(chart, labels, series) {
    if (!chart) return;
    chart.data.labels = labels;
    chart.data.datasets = series.map(({ label, data, color }) => ({
      label,
      data,
      borderColor:          color,
      backgroundColor:      _gradientFill(color),
      borderWidth:          2,
      pointRadius:          0,
      pointHoverRadius:     4,
      pointBackgroundColor: color,
      pointBorderColor:     '#fff',
      pointBorderWidth:     1,
      fill:                 true,
      tension:              0.4,
      spanGaps:             true,
    }));
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

/**
 * Look up a metric value at a given frame's epoch from metric events.
 * Falls back to null.
 * @param {object[]} metrics
 * @param {object} frame
 * @param {string} key
 */
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
