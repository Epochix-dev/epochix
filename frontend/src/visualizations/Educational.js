/**
 * Educational.js — "In plain English".
 *
 * A concise, friendly explainer for non-technical viewers: a one-line summary,
 * a Start → Learned → Now journey, a simple "gets X in 10 right" meter, and an
 * honest practice-vs-test analogy. All numbers come straight from the run.
 */
import { seriesFromMetrics } from '../viz-util.js';

const PHASE_EMOJI = {
  awakening: '🌱', learning: '📈', understanding: '💡', mastering: '🎯', polishing: '✨',
};

export class Educational {
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
    const frames = s.frames ?? [];
    const last = frames[frames.length - 1];
    const sig = `${frames.length}:${last?.primary_metric_value}:${last?.grade}:${(s.metrics ?? []).length}`;
    if (sig === this._sig) return;
    this._sig = sig;

    if (frames.length < 1 || last?.primary_metric_value == null) {
      this._el.innerHTML = `<div class="edu-empty">A plain-English summary appears once
        training is under way.</div>`;
      return;
    }

    const first = frames[0].primary_metric_value ?? last.primary_metric_value;
    const lastV = last.primary_metric_value;
    const epochs = Math.round(last.epoch ?? frames.length);
    const grade = last.grade ?? '—';
    const phase = last.phase ?? 'learning';

    // Infer direction from the data itself (the stored primary value can be an
    // accuracy even when run.primary_metric is named "val_loss"): a value bounded
    // in [0,1] that rises over training is accuracy-like.
    const vals = frames.map((f) => f.primary_metric_value).filter(Number.isFinite);
    const inUnit = vals.length > 0 && vals.every((v) => v >= 0 && v <= 1);
    const accLike = inUnit && lastV >= first;

    let lead;
    if (accLike) {
      lead = `Over <b>${epochs} epochs</b> your model went from <b>${_pct(first)}</b> to
        <b>${_pct(lastV)}</b> accuracy — earning a grade of <b>${_esc(grade)}</b>.`;
    } else if (lastV < first) {
      lead = `Over <b>${epochs} epochs</b> your model reduced its error from <b>${_num(first)}</b>
        to <b>${_num(lastV)}</b> — earning a grade of <b>${_esc(grade)}</b>.`;
    } else {
      lead = `Over <b>${epochs} epochs</b> your model moved from <b>${_num(first)}</b> to
        <b>${_num(lastV)}</b> — earning a grade of <b>${_esc(grade)}</b>.`;
    }

    const steps = `
      <div class="edu-step">
        <span class="edu-emoji">🌱</span>
        <div class="edu-step-body"><b>Started</b><span>${accLike ? _pct(first) : _num(first)} · knew little</span></div>
      </div>
      <div class="edu-arrow">→</div>
      <div class="edu-step">
        <span class="edu-emoji">${PHASE_EMOJI[phase] ?? '📈'}</span>
        <div class="edu-step-body"><b>Learned</b><span>found the patterns</span></div>
      </div>
      <div class="edu-arrow">→</div>
      <div class="edu-step is-now">
        <span class="edu-emoji">🎯</span>
        <div class="edu-step-body"><b>Now</b><span>${accLike ? _pct(lastV) : _num(lastV)} · grade ${_esc(grade)}</span></div>
      </div>`;

    const meter = accLike ? _meter(lastV) : '';
    const analogy = _analogy(s.metrics ?? [], accLike);

    this._el.innerHTML = `
      <div class="edu">
        <p class="edu-lead">${lead}</p>
        <div class="edu-journey">${steps}</div>
        ${meter}
        ${analogy ? `<p class="edu-analogy"><span>💡</span> ${analogy}</p>` : ''}
      </div>`;
  }
}

// ── pieces ──────────────────────────────────────────────────────────────────

function _meter(v) {
  const n = Math.round(v * 10);
  const dots = Array.from({ length: 10 }, (_, i) =>
    `<span class="edu-dot${i < n ? ' on' : ''}"></span>`).join('');
  return `
    <div class="edu-meter">
      <div class="edu-dots">${dots}</div>
      <span class="edu-meter-label">Gets about <b>${n} in 10</b> right on data it hasn't seen</span>
    </div>`;
}

function _analogy(metrics, accLike) {
  const acc = seriesFromMetrics(metrics, 'accuracy');
  const valAcc = seriesFromMetrics(metrics, 'val_accuracy');
  if (accLike && acc.length && valAcc.length) {
    const a = acc[acc.length - 1].y, v = valAcc[valAcc.length - 1].y;
    const gap = a - v;
    const verdict = gap > 0.12
      ? `a wide gap, so it partly <b>memorised</b> the practice set rather than learning the idea (overfitting).`
      : `a small gap, so it learned the real patterns rather than just memorising.`;
    return `Like a student: it scored <b>${_pct(a)}</b> on practice questions and
            <b>${_pct(v)}</b> on the real test — ${verdict}`;
  }
  const trainL = seriesFromMetrics(metrics, 'train_loss');
  const valL = seriesFromMetrics(metrics, 'val_loss');
  if (trainL.length && valL.length) {
    const t = trainL[trainL.length - 1].y, vv = valL[valL.length - 1].y;
    const verdict = (vv - t) > t * 0.45
      ? `the test error is much higher — a sign it <b>memorised</b> the training data (overfitting).`
      : `the two are close — a sign it learned to <b>generalise</b>.`;
    return `Its mistakes on training data (<b>${_num(t)}</b>) vs unseen data (<b>${_num(vv)}</b>):
            ${verdict}`;
  }
  return '';
}

// ── helpers ─────────────────────────────────────────────────────────────────

function _pct(v) { return `${(v * 100).toFixed(1)}%`; }
function _num(v) {
  if (!Number.isFinite(v)) return '—';
  if (Math.abs(v) >= 1) return v.toFixed(3);
  return v.toFixed(4);
}
function _esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
