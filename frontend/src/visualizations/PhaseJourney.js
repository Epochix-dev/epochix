/**
 * PhaseJourney.js — horizontal phase-timeline ribbon.
 *
 * Tells the run's story at a glance: the five learning phases
 * (awakening → polishing) mapped onto their epoch ranges, sized by how long
 * the model spent in each, annotated with the grade reached. Educational view
 * that no raw-curve tool (TensorBoard/W&B) offers.
 *
 * Pure vanilla JS reading store.frames + store.currentFrame.
 */

const PHASE_ORDER = ['awakening', 'learning', 'understanding', 'mastering', 'polishing'];

const PHASE_META = {
  awakening:     { icon: '🌱', label: 'Awakening',     plain: 'first signal from noise' },
  learning:      { icon: '📈', label: 'Learning',      plain: 'patterns forming' },
  understanding: { icon: '💡', label: 'Understanding', plain: 'beyond memorisation' },
  mastering:     { icon: '🎯', label: 'Mastering',     plain: 'refining the edges' },
  polishing:     { icon: '✨', label: 'Polishing',     plain: 'final gains' },
};

export class PhaseJourney {
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
    const segs = _segments(s.frames ?? []);
    const curEpoch = s.currentFrame?.epoch ?? null;

    // Skip rework if nothing changed (segment signature + current epoch)
    const sig = segs.map((g) => `${g.phase}:${g.startEpoch}-${g.endEpoch}:${g.grade}`).join('|') + `@${curEpoch}`;
    if (sig === this._sig) return;
    this._sig = sig;

    if (segs.length === 0) {
      this._el.innerHTML = `<div class="pj-empty">The phase journey unfolds as training runs…</div>`;
      return;
    }

    const totalSpan = Math.max(1, segs[segs.length - 1].endEpoch - segs[0].startEpoch + 1);

    const parts = [];
    segs.forEach((g, idx) => {
      const meta = PHASE_META[g.phase] ?? { icon: '•', label: g.phase, plain: '' };
      const widthPct = ((g.endEpoch - g.startEpoch + 1) / totalSpan) * 100;
      const active = curEpoch != null && curEpoch >= g.startEpoch && curEpoch <= g.endEpoch;
      const epochRange = g.startEpoch === g.endEpoch
        ? `ep ${g.startEpoch}` : `ep ${g.startEpoch}–${g.endEpoch}`;
      parts.push(`
        <div class="pj-seg${active ? ' is-active' : ''}"
             style="flex:${widthPct} 1 0; --pj-c:var(--phase-${g.phase}, var(--accent-primary))"
             title="${_esc(meta.label)} · ${_esc(epochRange)} · grade ${_esc(g.grade ?? '—')}">
          <div class="pj-seg-top">
            <span class="pj-seg-icon">${meta.icon}</span>
            <span class="pj-seg-grade">${_esc(g.grade ?? '')}</span>
          </div>
          <div class="pj-seg-name">${_esc(meta.label)}</div>
          <div class="pj-seg-sub">${_esc(meta.plain)}</div>
          <div class="pj-seg-range">${_esc(epochRange)}</div>
        </div>`);
      if (idx < segs.length - 1) parts.push(`<div class="pj-arrow">→</div>`);
    });

    this._el.innerHTML = `<div class="pj-bar">${parts.join('')}</div>`;
  }
}

/**
 * Collapse the frame stream into consecutive phase segments.
 * @param {object[]} frames
 * @returns {{phase:string,startEpoch:number,endEpoch:number,grade:string|null}[]}
 */
function _segments(frames) {
  const out = [];
  for (const f of frames) {
    const phase = f.phase ?? 'awakening';
    const epoch = f.epoch ?? out.length;
    const grade = f.grade ?? null;
    const last = out[out.length - 1];
    if (last && last.phase === phase) {
      last.endEpoch = epoch;
      last.grade = grade ?? last.grade;
    } else {
      out.push({ phase, startEpoch: epoch, endEpoch: epoch, grade });
    }
  }
  return out;
}

function _esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

export { PHASE_ORDER };
