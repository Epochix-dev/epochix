/**
 * Educational.js — "In plain English".
 *
 * A concise, friendly explainer for non-technical viewers: a one-line summary,
 * a Start → Learned → Now journey, a simple "gets X in 10 right" meter, and a
 * practised-vs-unseen analogy. All numbers come straight from the run.
 */
import { readGap } from '../generalisation.js';
import { escapeHtml as _esc } from '../escape.js';

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
    const analogy = _analogy(s.metrics ?? []);

    this._el.innerHTML = `
      <div class="edu">
        <p class="edu-lead">${lead}</p>
        <div class="edu-journey">${steps}</div>
        ${meter}
        ${analogy ? `<p class="edu-analogy"><span>💡</span><span>${analogy}</span></p>` : ''}
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

/**
 * The train/validation gap as a student's practice questions and unseen ones.
 *
 * It used to read "a small gap, so it learned the real patterns rather than
 * just memorising" for any accuracy gap under twelve points — on a run the
 * diagnostics card called overfitting. A gap alone shows neither; what the
 * numbers do show is how large it is and whether the score on unseen data is
 * still improving (generalisation.js).
 */
function _analogy(metrics) {
  const g = readGap(metrics);
  if (!g) return '';
  const since = g.bestEpoch == null ? '' : ` since epoch ${Math.round(g.bestEpoch)}`;

  if (g.kind === 'accuracy') {
    const points = `<b>${(g.gap * 100).toFixed(1)} points</b>`;
    let verdict;
    if (g.size === 'small') {
      verdict = `about the same, so what it learned carries over to new data.`;
    } else if (g.validation === 'at_best') {
      verdict = `a gap of ${points}. It knows its practice questions better than new ones,
        but it was still improving on new ones at the last reading.`;
    } else if (g.validation === 'past_best') {
      verdict = `a gap of ${points}, and its score on new questions has slipped${since} —
        it has started to <b>memorise</b> the practice set (overfitting).`;
    } else if (g.size === 'wide') {
      verdict = `a wide gap of ${points}: it knows its practice questions far better than
        new ones, which usually means it <b>memorised</b> part of them (overfitting).`;
    } else {
      verdict = `a gap of ${points}: it knows its practice questions better than new ones.`;
    }
    return `Like a student: it scored <b>${_pct(g.train)}</b> on the questions it practised on
            (training data) and <b>${_pct(g.val)}</b> on questions it had never seen
            (validation data) — ${verdict}`;
  }

  let verdict;
  if (g.size === 'small') {
    verdict = `close, so what it learned carries over to new data.`;
  } else if (g.validation === 'at_best') {
    verdict = `higher on new data, but still falling there at the last reading.`;
  } else if (g.validation === 'past_best') {
    verdict = `higher on new data, and rising there${since} — it has started to
      <b>memorise</b> the training data (overfitting).`;
  } else if (g.size === 'wide') {
    verdict = `much higher on new data, which usually means it <b>memorised</b> part of the
      training data (overfitting).`;
  } else {
    verdict = `higher on new data.`;
  }
  return `Its error on the data it trained on (<b>${_num(g.train)}</b>) vs data it had never
          seen (<b>${_num(g.val)}</b>): ${verdict}`;
}

// ── helpers ─────────────────────────────────────────────────────────────────

function _pct(v) { return `${(v * 100).toFixed(1)}%`; }
function _num(v) {
  if (!Number.isFinite(v)) return '—';
  if (Math.abs(v) >= 1) return v.toFixed(3);
  return v.toFixed(4);
}
