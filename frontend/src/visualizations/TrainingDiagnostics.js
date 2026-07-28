/**
 * TrainingDiagnostics.js — interpreted training-health dashboard.
 *
 * This is the differentiator vs TensorBoard / W&B / DVCLive: instead of just
 * drawing raw curves, it reads the metric series and tells the user what they
 * MEAN — overfitting gap, convergence status, best checkpoint, stability — in
 * both plain English (educational) and exact numbers (technical), plus an
 * overall health score.
 *
 * Pure vanilla JS. Reads store.metrics (canonical events) + store.frames.
 */

const STATUS_COLOR = {
  good:    '#34d399',
  warn:    '#fbbf24',
  bad:     '#f87171',
  neutral: '#60a5fa',
};

// Per-card glyphs for the gradient icon tile (Vision-UI stat-card style)
const CARD_ICONS = {
  'Overfitting':     '⚖',
  'Convergence':     '↘',
  'Best checkpoint': '★',
  'Stability':       '∿',
  'Generalisation':  '◎',
};

export class TrainingDiagnostics {
  /** @param {HTMLElement} container */
  constructor(container) {
    this._el = container;
    this._unsub = null;
    this._built = false;
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
    const d = _diagnose(s);
    if (!d) {
      if (!this._built) {
        this._el.innerHTML =
          `<div class="diag-empty">Diagnostics appear once metrics arrive…</div>`;
      }
      return;
    }
    this._built = true;

    const cards = [
      _gaugeCard(d.health),
      _card(d.overfit),
      _card(d.convergence),
      _card(d.best),
      _card(d.stability),
      _card(d.generalisation),
    ].join('');

    this._el.innerHTML = `<div class="diag-grid">${cards}</div>`;
  }
}

// ── diagnostics engine ──────────────────────────────────────────────────────

/** @param {import('../store.js').AppState} s */
function _diagnose(s) {
  const metrics = s.metrics ?? [];
  if (metrics.length === 0) return null;

  const trainLoss = _series(metrics, 'train_loss');
  const valLoss   = _series(metrics, 'val_loss');
  const acc       = _series(metrics, 'accuracy');
  const valAcc    = _series(metrics, 'val_accuracy');

  // Need at least one usable series
  if (trainLoss.length < 2 && valLoss.length < 2 && acc.length < 2 && valAcc.length < 2) {
    return null;
  }

  const overfit        = _diagnoseOverfit(trainLoss, valLoss, acc, valAcc);
  const convergence    = _diagnoseConvergence(valLoss.length >= 2 ? valLoss : trainLoss,
                                              valLoss.length >= 2 ? 'val loss' : 'train loss',
                                              trainLoss);
  const best           = _diagnoseBest(valLoss, valAcc, trainLoss, acc);
  const stability      = _diagnoseStability(trainLoss.length >= 3 ? trainLoss : valLoss);
  const generalisation = _diagnoseGeneralisation(valAcc, acc);

  const health = _healthScore({ overfit, convergence, stability, generalisation });

  return { overfit, convergence, best, stability, generalisation, health };
}

function _diagnoseOverfit(trainLoss, valLoss, acc, valAcc) {
  // Prefer loss gap; fall back to accuracy gap.
  if (trainLoss.length >= 1 && valLoss.length >= 1) {
    const tl = _last(trainLoss), vl = _last(valLoss);
    const gap = vl - tl;
    // Dividing by the training loss alone explodes as the model fits: a run at
    // train 0.01 / val 0.02 is excellent, yet scores 100% and reads
    // "memorises". Normalise by the LEVEL of the two losses instead, so the
    // ratio stays meaningful as both approach zero.
    const level = Math.max((Math.abs(tl) + Math.abs(vl)) / 2, 1e-6);
    const rel = gap / level;
    let status = 'good', verdict = 'Generalises well — barely any train/val gap.';
    if (rel > 0.45)      { status = 'bad';  verdict = 'Overfitting — it memorises training data more than it learns.'; }
    else if (rel > 0.18) { status = 'warn'; verdict = 'Mild overfitting starting to show.'; }
    return {
      label: 'Overfitting',
      status,
      big: (gap >= 0 ? '+' : '') + gap.toFixed(3),
      plain: verdict,
      tech: `val−train loss = ${gap.toFixed(3)} (${(rel * 100).toFixed(0)}% of the loss level)`,
    };
  }
  if (acc.length >= 1 && valAcc.length >= 1) {
    const a = _last(acc), v = _last(valAcc);
    const gap = a - v;
    let status = 'good', verdict = 'Validation tracks training closely.';
    if (gap > 0.12)      { status = 'bad';  verdict = 'Overfitting — much better on training than validation.'; }
    else if (gap > 0.05) { status = 'warn'; verdict = 'Small generalisation gap appearing.'; }
    return {
      label: 'Overfitting',
      status,
      big: (gap * 100).toFixed(1) + 'pp',
      plain: verdict,
      tech: `train−val acc = ${(gap * 100).toFixed(1)} percentage points`,
    };
  }
  return {
    label: 'Overfitting', status: 'neutral', big: 'n/a',
    plain: 'Add a validation metric to detect overfitting.',
    tech: 'No paired train/val series found.',
  };
}

function _diagnoseConvergence(series, name, trainLoss = []) {
  if (series.length < 2) {
    return { label: 'Convergence', status: 'neutral', big: '—',
             plain: 'Not enough epochs yet.', tech: `${name}: <2 points` };
  }
  const tail = series.slice(-Math.min(5, series.length));
  const slope = _slope(tail);                 // per-epoch change (absolute)
  const span  = tail[tail.length - 1].value - tail[0].value;
  // Scale-relative slope so the thresholds hold for any loss magnitude
  // (a 0.005/epoch drop is huge for a loss near 0.1 but noise for perplexity~300).
  const scale = Math.max(_mean(tail.map((p) => Math.abs(p.value))), 1e-6);
  const relSlope = slope / scale;             // fractional change per epoch
  // Loss: negative slope = improving.
  let status, verdict, head;
  if (relSlope < -0.01)      { status = 'good';    head = 'Improving';  verdict = `${name} is still dropping — more training will likely help.`; }
  else if (relSlope > 0.008) {
    status = 'bad'; head = 'Diverging';
    // A rising VALIDATION loss while training loss still falls is overfitting,
    // and the fix is to stop earlier — not to lower the learning rate. Only
    // when BOTH are rising is the step size the likely culprit. Telling every
    // overfitting run to lower its LR was advice for the wrong problem.
    const trainTail = trainLoss.slice(-Math.min(5, trainLoss.length));
    const trainRising = trainTail.length >= 2 && _slope(trainTail) > 0;
    verdict = trainRising
      ? `${name} and training loss are both rising — the step size is likely too large.`
      : `${name} is rising while training loss falls — that is overfitting; the best checkpoint is behind you.`;
  }
  else                       { status = 'warn';    head = 'Plateaued';  verdict = `${name} has flattened — near its best, consider stopping.`; }
  return {
    label: 'Convergence', status, big: head,
    plain: verdict,
    tech: `slope ${slope.toFixed(4)}/epoch (${(relSlope * 100).toFixed(1)}%) · Δ(last ${tail.length}) ${span.toFixed(3)}`,
  };
}

function _diagnoseBest(valLoss, valAcc, trainLoss, acc) {
  if (valAcc.length >= 1) {
    const b = _argbest(valAcc, 'max');
    return { label: 'Best checkpoint', status: 'neutral',
             big: `ep ${fmtEpoch(b.epoch)}`,
             plain: `Best validation accuracy reached at epoch ${fmtEpoch(b.epoch)}.`,
             tech: `val_acc max = ${(b.value * 100).toFixed(1)}% @ epoch ${fmtEpoch(b.epoch)}` };
  }
  if (valLoss.length >= 1) {
    const b = _argbest(valLoss, 'min');
    return { label: 'Best checkpoint', status: 'neutral',
             big: `ep ${fmtEpoch(b.epoch)}`,
             plain: `Lowest validation loss reached at epoch ${fmtEpoch(b.epoch)}.`,
             tech: `val_loss min = ${b.value.toFixed(3)} @ epoch ${fmtEpoch(b.epoch)}` };
  }
  const src = acc.length ? { s: acc, m: 'max', k: 'accuracy' } : { s: trainLoss, m: 'min', k: 'train_loss' };
  if (src.s.length >= 1) {
    const b = _argbest(src.s, src.m);
    const val = src.m === 'max' ? `${(b.value * 100).toFixed(1)}%` : b.value.toFixed(3);
    return { label: 'Best checkpoint', status: 'neutral', big: `ep ${fmtEpoch(b.epoch)}`,
             plain: `Best ${src.k} reached at epoch ${fmtEpoch(b.epoch)}.`,
             tech: `${src.k} ${src.m} = ${val} @ epoch ${fmtEpoch(b.epoch)}` };
  }
  return { label: 'Best checkpoint', status: 'neutral', big: '—', plain: 'No series yet.', tech: '' };
}

function _diagnoseStability(series) {
  if (series.length < 3) {
    return { label: 'Stability', status: 'neutral', big: '—',
             plain: 'Needs a few more epochs.', tech: 'σ of Δ: n/a' };
  }
  // Measure noise AROUND the trend, not the trend itself. The first differences
  // of a healthy run are dominated by the loss legitimately falling, so σ(Δ)
  // scores a textbook-clean run as unstable — measurably WORSE than a genuinely
  // noisy one (47% vs 46% on our own demo). Second differences cancel any
  // constant slope, leaving the epoch-to-epoch wobble; /√2 undoes the variance
  // doubling that differencing twice introduces.
  const d1 = [];
  for (let i = 1; i < series.length; i++) d1.push(series[i].value - series[i - 1].value);
  if (d1.length < 2) {
    return { label: 'Stability', status: 'neutral', big: '—',
             plain: 'Needs a few more epochs.', tech: 'detrended σ: n/a' };
  }
  const d2 = [];
  for (let i = 1; i < d1.length; i++) d2.push(d1[i] - d1[i - 1]);
  const sigma = _std(d2) / Math.SQRT2;
  const scale = Math.max(_mean(series.map((p) => Math.abs(p.value))), 1e-6);
  const rel = sigma / scale;
  let status = 'good', verdict = 'Smooth, steady training — no instability.';
  if (rel > 0.5)      { status = 'bad';  verdict = 'Noisy / unstable — loss bounces between epochs.'; }
  else if (rel > 0.2) { status = 'warn'; verdict = 'Some epoch-to-epoch jitter.'; }
  return { label: 'Stability', status, big: sigma.toFixed(3),
           plain: verdict,
           tech: `detrended σ = ${sigma.toFixed(4)} (${(rel * 100).toFixed(0)}% of level)` };
}

function _diagnoseGeneralisation(valAcc, acc) {
  const s = valAcc.length ? valAcc : acc;
  const k = valAcc.length ? 'validation' : 'training';
  if (s.length < 1) {
    return { label: 'Generalisation', status: 'neutral', big: '—',
             plain: 'No accuracy metric available.', tech: '' };
  }
  const v = _last(s);
  let status = 'warn';
  if (v >= 0.85) status = 'good';
  else if (v < 0.6) status = 'bad';
  return { label: 'Generalisation', status,
           big: `${(v * 100).toFixed(1)}%`,
           plain: `Currently ${(v * 100).toFixed(1)}% correct on ${k} data.`,
           tech: `latest ${valAcc.length ? 'val_accuracy' : 'accuracy'} = ${(v * 100).toFixed(1)}%` };
}

function _healthScore({ overfit, convergence, stability, generalisation }) {
  // A weighted blend of the four verdicts above — NOT a measured quantity, and
  // it has no meaning outside this dashboard. The weights are a judgement call.
  // It is labelled as such in the UI so a reader does not mistake a round
  // number for an instrument reading.
  const sc = { good: 1, warn: 0.55, bad: 0.2, neutral: 0.6 };
  const w  = { overfit: 0.3, convergence: 0.2, stability: 0.2, generalisation: 0.3 };
  const raw =
    sc[overfit.status]        * w.overfit +
    sc[convergence.status]    * w.convergence +
    sc[stability.status]      * w.stability +
    sc[generalisation.status] * w.generalisation;
  const score = Math.round(raw * 100);
  let status = 'good', verdict = 'Healthy run.';
  if (score < 45)      { status = 'bad';  verdict = 'Needs attention.'; }
  else if (score < 70) { status = 'warn'; verdict = 'Decent, with caveats.'; }
  return { score, status, verdict };
}

// ── card renderers ──────────────────────────────────────────────────────────

function _card(c) {
  const col  = STATUS_COLOR[c.status] ?? STATUS_COLOR.neutral;
  const icon = CARD_ICONS[c.label] ?? '•';
  return `
    <div class="diag-card" style="--diag-c:${col}">
      <div class="diag-card-head">
        <span class="diag-icon">${icon}</span>
        <span class="diag-label">${_esc(c.label)}</span>
        <span class="diag-chip">${_esc(_statusWord(c.status))}</span>
      </div>
      <div class="diag-big">${_esc(c.big)}</div>
      <div class="diag-plain">${_esc(c.plain)}</div>
      <div class="diag-tech">${_esc(c.tech)}</div>
    </div>`;
}

function _statusWord(status) {
  return { good: 'Good', warn: 'Watch', bad: 'Alert', neutral: 'Info' }[status] ?? '';
}

function _gaugeCard(h) {
  const col = STATUS_COLOR[h.status] ?? STATUS_COLOR.neutral;
  const deg = Math.round(h.score * 3.6);
  return `
    <div class="diag-card diag-gauge-card" style="--diag-c:${col}">
      <div class="diag-card-head">
        <span class="diag-label">Health score</span>
        <span class="diag-chip">${_esc(_statusWord(h.status))}</span>
      </div>
      <div class="diag-gauge" style="background:conic-gradient(${col} ${deg}deg, var(--border-subtle) 0deg)">
        <div class="diag-gauge-hole">
          <span class="diag-gauge-num">${h.score}</span>
        </div>
      </div>
      <div class="diag-plain">${_esc(h.verdict)}</div>
      <div class="diag-tech">summary of the four checks above — not a measured quantity</div>
    </div>`;
}

// ── series helpers ──────────────────────────────────────────────────────────

function _series(metrics, key) {
  return metrics
    .filter((m) => m.canonical_key === key && Number.isFinite(m.value))
    .map((m) => ({ epoch: m.epoch ?? 0, value: m.value }))
    .sort((a, b) => a.epoch - b.epoch);
}
function _last(s)  { return s[s.length - 1].value; }
function _mean(a)  { return a.reduce((x, y) => x + y, 0) / (a.length || 1); }
function _std(a)   { const m = _mean(a); return Math.sqrt(_mean(a.map((x) => (x - m) ** 2))); }
function _argbest(s, mode) {
  let best = s[0];
  for (const p of s) {
    if (mode === 'max' ? p.value > best.value : p.value < best.value) best = p;
  }
  return best;
}
/** Least-squares slope of {epoch,value} points (per-epoch). */
function _slope(pts) {
  const n = pts.length;
  const mx = _mean(pts.map((p) => p.epoch));
  const my = _mean(pts.map((p) => p.value));
  let num = 0, den = 0;
  for (const p of pts) { num += (p.epoch - mx) * (p.value - my); den += (p.epoch - mx) ** 2; }
  return den === 0 ? 0 : num / den;
}
function fmtEpoch(e) { return Number.isInteger(e) ? String(e) : e.toFixed(0); }

function _esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
