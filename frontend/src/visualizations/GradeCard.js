/**
 * GradeCard.js — animated letter-grade display.
 *
 * Renders an oversized grade letter that cross-fades and shifts colour
 * as the grade changes during training.
 */

const GRADE_COLORS = {
  'A+': '#52e88a',
  'A':  '#3cd06a',
  'A-': '#7ee84a',
  'B+': '#60a5fa',
  'B':  '#4a8cf7',
  'B-': '#7bb4f8',
  'C+': '#fb923c',
  'C':  '#fbbf24',
  'C-': '#fcd34d',
  'D':  '#f97316',
  'F':  '#ef4444',
  'I':  '#6b7280',
};

export class GradeCard {
  /**
   * @param {HTMLElement} container
   */
  constructor(container) {
    this._el = container;
    this._currentGrade = null;
    this._render();
  }

  /** @param {import('../store.js').AppState} store */
  mount(store) {
    this._unsub = store.subscribe((s) => {
      const g = s.currentFrame?.grade ?? null;
      if (g !== this._currentGrade) {
        this._currentGrade = g;
        this._update();
      }
    });
  }

  unmount() {
    if (this._unsub) this._unsub();
  }

  // ── internal ──────────────────────────────────────────────────────────────

  _render() {
    this._el.innerHTML = `
      <div class="grade-card">
        <span class="grade-letter" id="grade-letter">—</span>
        <span class="grade-label">Grade</span>
      </div>
    `;
    this._letterEl = this._el.querySelector('#grade-letter');
  }

  _update() {
    const g   = this._currentGrade ?? '—';
    const col = GRADE_COLORS[g] ?? '#6b7280';
    const el  = this._letterEl;

    el.style.transition = 'color 600ms ease, transform 300ms ease, text-shadow 600ms ease';
    el.style.transform  = 'scale(1.15)';

    setTimeout(() => {
      el.textContent   = g;
      el.style.color   = col;
      el.style.textShadow = `0 0 24px ${col}80`;
    }, 80);

    setTimeout(() => {
      el.style.transform = 'scale(1)';
    }, 250);
  }
}

// Inject grade card styles once
if (!document.getElementById('grade-card-styles')) {
  const s = document.createElement('style');
  s.id = 'grade-card-styles';
  s.textContent = `
    .grade-card {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 2px;
    }
    .grade-letter {
      font-family: var(--font-serif);
      font-size: 72px;
      line-height: 1;
      font-weight: 400;
      color: var(--text-muted);
      letter-spacing: -2px;
      transition: color 600ms ease;
      user-select: none;
    }
    .grade-label {
      font-size: 10px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      color: var(--text-muted);
    }
  `;
  document.head.appendChild(s);
}
