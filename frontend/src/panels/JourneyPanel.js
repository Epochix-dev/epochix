/**
 * JourneyPanel.js — grade card, narrative, stat row, metaphor cards,
 *                    timeline + epoch scrubber.
 */

import { GradeCard }       from '../visualizations/GradeCard.js';
import { TimelineStory }   from '../visualizations/TimelineStory.js';
import { EpochScrubber }   from '../visualizations/EpochScrubber.js';
import { GradeArcChart }   from '../visualizations/GradeArcChart.js';

const PHASE_ICON = {
  awakening:     '🌱',
  learning:      '📈',
  understanding: '💡',
  mastering:     '🎯',
  polishing:     '✨',
};

export class JourneyPanel {
  constructor(store, i18n) {
    this._store    = store;
    this._i18n     = i18n;
    this._unsub    = null;
    this._grade    = null;
    this._timeline = null;
    this._scrubber = null;
    this._arc      = null;
    this._statEls  = null;
  }

  mount() {
    // Grade card
    const gradeWrap = document.getElementById('grade-card-wrap');
    if (gradeWrap) {
      this._grade = new GradeCard(gradeWrap);
      this._grade.mount(this._store);
    }

    // Grade arc chart (central learning curve)
    const arcCanvas = document.getElementById('grade-arc-chart');
    if (arcCanvas) {
      this._arc = new GradeArcChart(arcCanvas);
      this._arc.mount(this._store);
    }

    // Narrative + metaphors react to store
    this._unsub = this._store.subscribe((s) => this._render(s));
    this._render(this._store.get());

    // Timeline
    const timelineEl = document.getElementById('timeline-story');
    if (timelineEl) {
      this._timeline = new TimelineStory(timelineEl, this._i18n.milestones ?? {});
      this._timeline.mount(this._store);
    }

    // Epoch scrubber
    const scrubWrap = document.getElementById('epoch-scrubber-wrap');
    if (scrubWrap) {
      this._scrubber = new EpochScrubber(scrubWrap);
      this._scrubber.mount(this._store);
    }
  }

  unmount() {
    if (this._unsub)    this._unsub();
    if (this._grade)    this._grade.unmount();
    if (this._arc)      this._arc.unmount();
    if (this._timeline) this._timeline.unmount();
    if (this._scrubber) this._scrubber.unmount();
  }

  // ── internal ──────────────────────────────────────────────────────────────

  _render(s) {
    const frame = s.currentFrame;
    const run   = s.run;

    // ── Narrative text ──────────────────────────────────────────────────────
    const el = document.getElementById('narrative-text');
    if (el) {
      if (frame?.narrative) {
        el.innerHTML = `<p class="narrative-live">${_esc(frame.narrative)}</p>`;
      } else if (!s.live && !frame) {
        el.innerHTML = `<p class="narrative-placeholder">Waiting for training data…</p>`;
      }
    }

    // ── Stat row (epoch / accuracy / progress / grade) ──────────────────────
    // Stable DOM nodes + animated count-up so the numbers feel alive.
    const statRow = document.getElementById('stat-row');
    if (statRow && frame) {
      if (!this._statEls) {
        statRow.innerHTML = `
          <span class="stat"><span class="stat-label">Epoch</span><span class="stat-val" data-k="epoch">—</span></span>
          <span class="stat"><span class="stat-label">Accuracy</span><span class="stat-val" data-k="acc">—</span></span>
          <span class="stat"><span class="stat-label">Progress</span><span class="stat-val" data-k="prog">—</span></span>
          <span class="stat"><span class="stat-label">Grade</span><span class="stat-val" data-k="grade">—</span></span>`;
        this._statEls = {
          epoch: statRow.querySelector('[data-k="epoch"]'),
          acc:   statRow.querySelector('[data-k="acc"]'),
          prog:  statRow.querySelector('[data-k="prog"]'),
          grade: statRow.querySelector('[data-k="grade"]'),
        };
      }
      if (frame.epoch != null) _countUp(this._statEls.epoch, frame.epoch, { decimals: 0 });
      if (frame.primary_metric_value != null)
        _countUp(this._statEls.acc, frame.primary_metric_value * 100, { decimals: 1, suffix: '%' });
      if (frame.progress != null)
        _countUp(this._statEls.prog, frame.progress * 100, { decimals: 0, suffix: '% done' });
      if (frame.grade) this._statEls.grade.textContent = frame.grade;
    }

    // ── Metaphor cards  ─────────────────────────────────────────────────────
    // Model uses { title, body, icon } — render all three.
    const mc = document.getElementById('metaphor-cards');
    if (mc && frame?.metaphor_cards?.length) {
      mc.innerHTML = frame.metaphor_cards
        .slice(0, 4)
        .map((c) => {
          const icon  = c.icon  ?? c.emoji ?? '🔹';
          const title = c.title ?? '';
          const body  = c.body  ?? c.description ?? '';
          return `
            <div class="metaphor-card">
              <div class="mc-title">${_esc(title)}</div>
              <div class="mc-body">${_esc(body)}</div>
            </div>
          `;
        })
        .join('');
    }

    // ── Phase badge ─────────────────────────────────────────────────────────
    // i18n labels already carry the emoji; only prepend the icon on raw fallback.
    const phaseBadge = document.getElementById('phase-badge');
    if (phaseBadge && frame?.phase) {
      phaseBadge.textContent = _phaseLabel(this._i18n, frame.phase);
      phaseBadge.style.borderColor = `var(--phase-${frame.phase}, var(--border-default))`;
    }

    // ── Grade pill in header ────────────────────────────────────────────────
    const gradePill = document.getElementById('grade-pill');
    if (gradePill && frame?.grade) {
      gradePill.textContent = frame.grade;
      const gradeKey = frame.grade.replace('+', '-plus').replace('-', '-minus').toLowerCase();
      gradePill.style.background = `var(--grade-${gradeKey}, var(--accent-primary))`;
      gradePill.style.color      = '#000';
    }

    // ── Run name ────────────────────────────────────────────────────────────
    const runNameEl = document.getElementById('run-name');
    if (runNameEl && run?.name) {
      runNameEl.textContent = run.name;
    }

    // ── Sidebar summary card (grade + phase) ─────────────────────────────────
    const scGrade = document.getElementById('sc-grade');
    if (scGrade && frame?.grade) scGrade.textContent = frame.grade;
    const scPhase = document.getElementById('sc-phase');
    if (scPhase && frame?.phase) {
      scPhase.textContent = _phaseLabel(this._i18n, frame.phase);
    }

    // ── Sidebar sparkline (accuracy trend) ───────────────────────────────────
    _renderSparkline(document.getElementById('sc-spark'), s.frames ?? []);
  }
}

function _esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

/** Phase label with emoji — uses i18n (already has emoji) or icon+name fallback. */
function _phaseLabel(i18n, phase) {
  return i18n?.phases?.[phase] ?? `${PHASE_ICON[phase] ?? ''} ${phase}`.trim();
}

/**
 * Render a tiny gradient area sparkline of the primary metric over epochs.
 * @param {SVGElement|null} svg
 * @param {object[]} frames
 */
function _renderSparkline(svg, frames) {
  if (!svg) return;
  const pts = frames
    .map((f) => f.primary_metric_value)
    .filter((v) => Number.isFinite(v));
  if (pts.length < 2) { svg.hidden = true; return; }

  const sig = pts.map((v) => v.toFixed(3)).join(',');
  if (svg.dataset.sig === sig) return;     // no change → skip
  svg.dataset.sig = sig;
  svg.hidden = false;

  const W = 120, H = 34, PAD = 3;
  const min = Math.min(...pts), max = Math.max(...pts);
  const span = max - min || 1;
  const x = (i) => PAD + (i / (pts.length - 1)) * (W - PAD * 2);
  const y = (v) => PAD + (1 - (v - min) / span) * (H - PAD * 2);

  let line = '';
  pts.forEach((v, i) => { line += `${i === 0 ? 'M' : 'L'} ${x(i).toFixed(1)} ${y(v).toFixed(1)} `; });
  const area = `${line} L ${x(pts.length - 1).toFixed(1)} ${H} L ${x(0).toFixed(1)} ${H} Z`;

  svg.innerHTML = `
    <defs>
      <linearGradient id="spark-fill" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"  stop-color="#7c6dff" stop-opacity="0.55"/>
        <stop offset="100%" stop-color="#7c6dff" stop-opacity="0"/>
      </linearGradient>
      <linearGradient id="spark-line" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0%" stop-color="#22d3ee"/>
        <stop offset="100%" stop-color="#7c6dff"/>
      </linearGradient>
    </defs>
    <path d="${area}" fill="url(#spark-fill)"/>
    <path d="${line}" fill="none" stroke="url(#spark-line)" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/>`;
}

/**
 * Animate an element's text from its last value up to `to` with easing.
 * Stores the current value on the element so re-renders continue smoothly.
 * @param {HTMLElement} el
 * @param {number} to
 * @param {{decimals?:number, suffix?:string, dur?:number}} [opts]
 */
function _countUp(el, to, opts = {}) {
  if (!el) return;
  const { decimals = 0, suffix = '', dur = 600 } = opts;
  const from = Number.parseFloat(el.dataset.cur ?? '');
  if (!Number.isFinite(from)) {
    el.textContent = to.toFixed(decimals) + suffix;
    el.dataset.cur = String(to);
    return;
  }
  if (Math.abs(from - to) < 1e-9) {
    el.textContent = to.toFixed(decimals) + suffix;
    return;
  }
  if (el._raf) cancelAnimationFrame(el._raf);
  const start = performance.now();
  const step = (now) => {
    const p = Math.min(1, (now - start) / dur);
    const eased = 1 - Math.pow(1 - p, 3);
    const v = from + (to - from) * eased;
    el.textContent = v.toFixed(decimals) + suffix;
    if (p < 1) {
      el._raf = requestAnimationFrame(step);
    } else {
      el.dataset.cur = String(to);
      el._raf = null;
    }
  };
  el._raf = requestAnimationFrame(step);
}
