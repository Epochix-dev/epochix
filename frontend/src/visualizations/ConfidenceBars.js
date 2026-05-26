/**
 * ConfidenceBars.js — "Live Metrics" as scalar cards.
 *
 * One card per metric (TensorBoard scalar-card style): big latest value, a ↑/↓
 * delta vs the previous epoch coloured by whether it improved, and a gradient
 * sparkline of the whole trend.
 */
import { emaSmooth, LOWER_IS_BETTER, metricLabel, seriesFromMetrics } from '../viz-util.js';

export class ConfidenceBars {
  /** @param {HTMLElement} container */
  constructor(container) {
    this._el = container;
    this._unsub = null;
    this._sig = '';
  }

  /** @param {import('../store.js').AppState} store */
  mount(store) {
    this._render(store.get());
    this._unsub = store.subscribe((s) => this._render(s));
  }

  unmount() {
    if (this._unsub) this._unsub();
  }

  // ── internal ──────────────────────────────────────────────────────────────

  _render(s) {
    const keys = _keys(s);
    if (keys.length === 0) return;

    // Build per-metric series.
    const cards = keys.map((key) => {
      const series = _seriesFor(s, key);
      const ys = series.map((p) => p.y);
      const latest = ys[ys.length - 1];
      const prev = ys.length > 1 ? ys[ys.length - 2] : latest;
      return { key, ys, latest, delta: latest - prev };
    }).filter((c) => Number.isFinite(c.latest));

    const sig = cards.map((c) => `${c.key}:${c.latest}:${c.ys.length}`).join('|');
    if (sig === this._sig) return;       // nothing changed
    this._sig = sig;

    this._el.innerHTML = `<div class="metric-cards">${cards.map(_card).join('')}</div>`;
  }
}

function _card(c) {
  const lower = LOWER_IS_BETTER.has(c.key);
  const improved = c.delta === 0 ? null : (lower ? c.delta < 0 : c.delta > 0);
  const arrow = c.delta > 1e-9 ? '▲' : (c.delta < -1e-9 ? '▼' : '·');
  const cls = improved == null ? 'flat' : (improved ? 'good' : 'bad');
  const col = lower ? '#fb923c' : '#7c6dff';
  return `
    <div class="mc">
      <div class="mc-top">
        <span class="mc-name" title="${_esc(c.key)}">${_esc(metricLabel(c.key))}</span>
        <span class="mc-delta ${cls}">${arrow} ${_fmt(Math.abs(c.delta))}</span>
      </div>
      <div class="mc-value">${_fmt(c.latest)}</div>
      ${_spark(c.ys, col)}
    </div>`;
}

/** Tiny gradient-area sparkline SVG for a value series. */
function _spark(values, color) {
  const v = emaSmooth(values, 0.2).filter(Number.isFinite);
  if (v.length < 2) return '<svg class="mc-spark" viewBox="0 0 100 28"></svg>';
  const min = Math.min(...v), max = Math.max(...v), span = max - min || 1;
  const x = (i) => (i / (v.length - 1)) * 100;
  const y = (val) => 26 - ((val - min) / span) * 24 - 1;
  let line = '';
  v.forEach((val, i) => { line += `${i ? 'L' : 'M'} ${x(i).toFixed(1)} ${y(val).toFixed(1)} `; });
  const area = `${line} L 100 28 L 0 28 Z`;
  const gid = `sp-${Math.random().toString(36).slice(2, 7)}`;
  return `
    <svg class="mc-spark" viewBox="0 0 100 28" preserveAspectRatio="none">
      <defs><linearGradient id="${gid}" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="${color}" stop-opacity="0.45"/>
        <stop offset="100%" stop-color="${color}" stop-opacity="0"/>
      </linearGradient></defs>
      <path d="${area}" fill="url(#${gid})"/>
      <path d="${line}" fill="none" stroke="${color}" stroke-width="1.6"
            stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/>
    </svg>`;
}

// ── data ────────────────────────────────────────────────────────────────────

function _keys(s) {
  const metrics = s.metrics ?? [];
  if (metrics.length > 0) {
    const seen = [];
    for (const m of metrics) if (!seen.includes(m.canonical_key)) seen.push(m.canonical_key);
    return seen.slice(0, 8);
  }
  // Fallback to frame skill_dimensions when no metric events exist.
  const sk = s.currentFrame?.skill_dimensions;
  return sk ? Object.keys(sk).slice(0, 8) : [];
}

function _seriesFor(s, key) {
  const fromMetrics = seriesFromMetrics(s.metrics ?? [], key);
  if (fromMetrics.length) return fromMetrics;
  // Fallback: single point from skill_dimensions.
  const val = s.currentFrame?.skill_dimensions?.[key];
  return Number.isFinite(val) ? [{ x: 0, y: val }] : [];
}

function _fmt(v) {
  if (!Number.isFinite(v)) return '—';
  if (Math.abs(v) >= 100) return v.toFixed(1);
  if (Math.abs(v) >= 1) return v.toFixed(3);
  return v.toFixed(4);
}
function _esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
