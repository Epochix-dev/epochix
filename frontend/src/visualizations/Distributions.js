/**
 * Distributions.js — "what's inside the model & the spread of its metrics".
 *
 * Two data-grounded views (no fabricated weight histograms):
 *  1. Parameter share by layer — where the model's capacity lives, from the
 *     detected architecture (bars sized by param count, coloured by layer type).
 *  2. Metric spread — a box-summary (min · IQR · median · last · max) per metric
 *     over the run, the honest analogue of TensorBoard's distributions.
 */
import { LOWER_IS_BETTER, metricLabel } from '../viz-util.js';

const TYPE_COLOR = {
  input: '#34d399', output: '#f472b6', conv: '#818cf8', dense: '#fbbf24',
  recurrent: '#22d3ee', attention: '#a78bfa', norm: '#6b7280', generic: '#60a5fa',
};

export class Distributions {
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
    const arch = s.architecture ?? [];
    const metrics = s.metrics ?? [];
    const sig = `${arch.length}:${metrics.length}`;
    if (sig === this._sig) return;          // avoid needless re-render
    this._sig = sig;

    const params = _paramSection(arch);
    const spread = _spreadSection(metrics);
    const hist = _histogramSection(metrics);
    if (!params && !spread && !hist) {
      this._el.innerHTML = `<div class="dist-empty">Distributions appear once the model
        architecture or metrics are available.</div>`;
      return;
    }
    this._el.innerHTML = `<div class="dist-grid">${params}${spread}${hist}</div>`;
  }
}

// ── section: parameter share by layer ───────────────────────────────────────

function _paramSection(arch) {
  const withParams = arch.filter((l) => (l.params ?? 0) > 0);
  if (withParams.length === 0) return '';
  const total = withParams.reduce((s, l) => s + l.params, 0);
  const max = Math.max(...withParams.map((l) => l.params));

  const rows = withParams.map((l) => {
    const pct = ((l.params / total) * 100);
    const w = (l.params / max) * 100;
    const col = TYPE_COLOR[l.visual_type] ?? TYPE_COLOR.generic;
    return `
      <div class="dist-row">
        <span class="dist-row-label" title="${_esc(l.layer_type)}">${_esc(l.tech_label)}</span>
        <div class="dist-bar-track">
          <div class="dist-bar-fill" style="width:${w.toFixed(1)}%;background:${col}"></div>
        </div>
        <span class="dist-row-val">${_fmt(l.params)} <span class="dist-pct">${pct.toFixed(0)}%</span></span>
      </div>`;
  }).join('');

  return `
    <div class="dist-card">
      <div class="dist-head">Parameter share by layer
        <span class="dist-sub">${_fmt(total)} total params · where capacity lives</span>
      </div>
      ${rows}
    </div>`;
}

// ── section: metric spread (box summary) ─────────────────────────────────────

function _spreadSection(metrics) {
  const byKey = new Map();
  for (const m of metrics) {
    if (!Number.isFinite(m.value)) continue;
    let arr = byKey.get(m.canonical_key);
    if (!arr) { arr = []; byKey.set(m.canonical_key, arr); }
    arr.push(m.value);
  }
  if (byKey.size === 0) return '';

  const rows = [...byKey.entries()].map(([key, vals]) => {
    const v = vals.slice().sort((a, b) => a - b);
    const min = v[0], max = v[v.length - 1];
    const q = (p) => v[Math.min(v.length - 1, Math.floor(p * (v.length - 1)))];
    const med = q(0.5), q1 = q(0.25), q3 = q(0.75);
    const last = vals[vals.length - 1];
    const span = max - min || 1;
    const pos = (x) => ((x - min) / span) * 100;
    const better = LOWER_IS_BETTER.has(key) ? '↓' : '↑';
    return `
      <div class="dist-row">
        <span class="dist-row-label" title="${_esc(key)}">${_esc(metricLabel(key))}</span>
        <div class="dist-box-track">
          <div class="dist-box-iqr" style="left:${pos(q1).toFixed(1)}%;width:${(pos(q3) - pos(q1)).toFixed(1)}%"></div>
          <div class="dist-box-med" style="left:${pos(med).toFixed(1)}%"></div>
          <div class="dist-box-last" style="left:${pos(last).toFixed(1)}%" title="latest ${_num(last)}"></div>
        </div>
        <span class="dist-row-val">${_num(last)} <span class="dist-pct">${better}</span></span>
      </div>`;
  }).join('');

  return `
    <div class="dist-card">
      <div class="dist-head">Metric spread
        <span class="dist-sub">min · IQR · median ▏ · latest ● · max</span>
      </div>
      ${rows}
    </div>`;
}

// ── section: value histograms (binned distribution per metric) ──────────────

function _histogramSection(metrics) {
  const byKey = new Map();
  for (const m of metrics) {
    if (!Number.isFinite(m.value)) continue;
    let arr = byKey.get(m.canonical_key);
    if (!arr) { arr = []; byKey.set(m.canonical_key, arr); }
    arr.push(m.value);
  }
  if (byKey.size === 0) return '';

  const rows = [...byKey.entries()].map(([key, vals]) => {
    const col = LOWER_IS_BETTER.has(key) ? '#fb923c' : '#7c6dff';
    return `
      <div class="dist-hrow">
        <span class="dist-row-label" title="${_esc(key)}">${_esc(metricLabel(key))}</span>
        ${_histogram(vals, col)}
        <span class="dist-row-val">n=${vals.length}</span>
      </div>`;
  }).join('');

  return `
    <div class="dist-card">
      <div class="dist-head">Value histograms
        <span class="dist-sub">how often each value occurred over training</span>
      </div>
      ${rows}
    </div>`;
}

/** Binned histogram (SVG bars) of a value series. */
function _histogram(values, color) {
  const BINS = 12;
  const min = Math.min(...values), max = Math.max(...values);
  const span = max - min || 1;
  const counts = new Array(BINS).fill(0);
  for (const v of values) {
    const b = Math.min(BINS - 1, Math.floor(((v - min) / span) * BINS));
    counts[b] += 1;
  }
  const maxC = Math.max(...counts, 1);
  const bw = 100 / BINS;
  const bars = counts.map((c, i) => {
    const h = (c / maxC) * 22;
    return `<rect x="${(i * bw + 0.6).toFixed(2)}" y="${(24 - h).toFixed(2)}"
      width="${(bw - 1.2).toFixed(2)}" height="${h.toFixed(2)}" rx="0.6"
      fill="${color}" opacity="${c ? 0.85 : 0.15}"></rect>`;
  }).join('');
  return `<svg class="dist-hist" viewBox="0 0 100 24" preserveAspectRatio="none">${bars}</svg>`;
}

// ── helpers ─────────────────────────────────────────────────────────────────

function _fmt(n) {
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
  return String(n);
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
