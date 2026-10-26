/**
 * Educational.js — "In plain English".
 *
 * A concise, friendly explainer for non-technical viewers: a one-line summary,
 * a Start → Learned → Now journey, a simple "gets X in 10 right" meter, and a
 * practised-vs-unseen analogy. All numbers come straight from the run.
 */
import { readGap } from '../generalisation.js';
import { escapeHtml as _esc } from '../escape.js';
import { LOWER_IS_BETTER, latestPrimaryKey, metricLabel } from '../viz-util.js';

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
    const epochs = _epochsTold(frames);
    const grade = last.grade ?? '—';
    const phase = last.phase ?? 'learning';

    // Say only what the metric's name supports. The panel used to call any
    // value between 0 and 1 that rose "accuracy" and count it as "N in 10
    // right on data it hasn't seen": an AUC, an F1, an mAP50 or CatBoost's
    // unnamed score were all told that way. The frames name the metric (the
    // run record can still hold its creation-time placeholder).
    const key = latestPrimaryKey(frames);
    const label = metricLabel(key ?? 'metric');
    const isAccuracy = key === 'accuracy' || key === 'val_accuracy';
    const lowerBetter =
      key != null && (LOWER_IS_BETTER.has(key) || LOWER_IS_BETTER.has(key.replace(/^val_/, '')));
    const show = (v) => (isAccuracy ? _pct(v) : _num(v));

    let lead;
    if (isAccuracy) {
      lead = `Over <b>${epochs} epochs</b> your model went from <b>${_pct(first)}</b> to
        <b>${_pct(lastV)}</b> accuracy — earning a grade of <b>${_esc(grade)}</b>.`;
    } else if (lowerBetter && lastV < first) {
      lead = `Over <b>${epochs} epochs</b> your model reduced its ${_esc(label)} from
        <b>${_num(first)}</b> to <b>${_num(lastV)}</b> — earning a grade of <b>${_esc(grade)}</b>.`;
    } else {
      lead = `Over <b>${epochs} epochs</b> its ${_esc(label)} went from <b>${_num(first)}</b> to
        <b>${_num(lastV)}</b> — earning a grade of <b>${_esc(grade)}</b>.`;
    }

    // What happened between the first reading and now, as a number. It read
    // "knew little" and "found the patterns" for every run, whatever it did.
    // "Learned" only where the name says which way is better.
    const improved = isAccuracy ? lastV > first : lowerBetter ? lastV < first : false;
    const moved = isAccuracy
      ? `${lastV >= first ? '+' : ''}${((lastV - first) * 100).toFixed(1)} points since then`
      : `${lastV >= first ? '+' : '−'}${_num(Math.abs(lastV - first))} since then`;

    const steps = `
      <div class="edu-step">
        <span class="edu-emoji">🌱</span>
        <div class="edu-step-body"><b>Started</b><span>${show(first)} · first reading</span></div>
      </div>
      <div class="edu-arrow">→</div>
      <div class="edu-step">
        <span class="edu-emoji">${PHASE_EMOJI[phase] ?? '📈'}</span>
        <div class="edu-step-body"><b>${improved ? 'Learned' : 'Changed'}</b><span>${moved}</span></div>
      </div>
      <div class="edu-arrow">→</div>
      <div class="edu-step is-now">
        <span class="edu-emoji">🎯</span>
        <div class="edu-step-body"><b>Now</b><span>${show(lastV)} · grade ${_esc(grade)}</span></div>
      </div>`;

    // "Right on data it hasn't seen" is true only of validation accuracy:
    // training accuracy was measured on the data it learned from.
    const meter = key === 'val_accuracy' ? _meter(lastV) : '';
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
  // Rounded to the nearest tenth — except upward to a full ten: 95.1% read
  // "about 10 in 10", which says it is never wrong.
  let n = Math.round(v * 10);
  let amount = `about <b>${n} in 10</b>`;
  if (n === 10 && v < 0.995) {
    n = 9;
    amount = `more than <b>9 in 10</b>`;
  }
  const dots = Array.from({ length: 10 }, (_, i) =>
    `<span class="edu-dot${i < n ? ' on' : ''}"></span>`).join('');
  return `
    <div class="edu-meter">
      <div class="edu-dots">${dots}</div>
      <span class="edu-meter-label">Gets ${amount} right on data it hasn't seen</span>
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

/**
 * How many epochs the story spans. It was the last epoch's number, one short
 * for every log that counts from 0 (CatBoost, XGBoost, Lightning's
 * `Epoch 0:`): sixty rounds read "over 59 epochs". Whole-numbered epochs are
 * counted from the first reading to the last; fractional ones (a Trainer
 * logging every half epoch) keep the last epoch's number.
 */
function _epochsTold(frames) {
  const epochs = frames.map((f) => f.epoch).filter(Number.isFinite);
  if (epochs.length === 0) return frames.length;
  const first = epochs[0];
  const last = epochs[epochs.length - 1];
  if (epochs.every(Number.isInteger)) return last - first + 1;
  return Math.round(last);
}

function _pct(v) { return `${(v * 100).toFixed(1)}%`; }
function _num(v) {
  if (!Number.isFinite(v)) return '—';
  if (Math.abs(v) >= 1) return v.toFixed(3);
  return v.toFixed(4);
}
