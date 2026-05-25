/**
 * TimelineStory.js — milestone and warning cards in a scrolling timeline.
 *
 * New cards animate in from below. Warning cards are styled differently.
 * Scrolls to latest card automatically when not user-scrolling.
 */

const MILESTONE_EMOJIS = {
  first_above_25:    '🎯',
  first_above_50:    '🌟',
  first_above_75:    '🚀',
  first_above_90:    '🏆',
  best_so_far:       '✅',
  biggest_jump:      '⚡',
  overfit_warning:   '⚠️',
  plateau:           '😴',
  lr_drop:           '📉',
  divergence:        '💥',
  training_complete: '🎓',
};

export class TimelineStory {
  /**
   * @param {HTMLElement} container
   * @param {Record<string,any>} i18n  - milestones sub-object of locale
   */
  constructor(container, i18n = {}) {
    this._el = container;
    this._i18n = i18n;
    this._seen = new Set();
    this._userScrolled = false;
    this._unsub = null;
    this._setupScrollDetection();
  }

  /** @param {import('../store.js').AppState} store */
  mount(store) {
    this._unsub = store.subscribe((s) => this._onState(s));
    this._onState(store.get());
  }

  unmount() {
    if (this._unsub) this._unsub();
  }

  // ── internal ──────────────────────────────────────────────────────────────

  _setupScrollDetection() {
    this._el.addEventListener('scroll', () => {
      const el = this._el;
      const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 32;
      this._userScrolled = !atBottom;
    }, { passive: true });
  }

  /** @param {import('../store.js').AppState} s */
  _onState(s) {
    // Render milestones
    for (const m of s.milestones) {
      const key = `m:${m.kind}:${m.epoch}`;
      if (!this._seen.has(key)) {
        this._seen.add(key);
        this._appendCard({
          emoji: MILESTONE_EMOJIS[m.kind] ?? '📌',
          title: this._i18n[m.kind] ?? m.kind,
          message: m.message ?? '',
          epoch: m.epoch,
          warning: m.kind === 'overfit_warning' || m.kind === 'plateau' || m.kind === 'divergence',
        });
      }
    }

    // Render training_complete if run is done
    if (!s.live && s.run && !this._seen.has('complete')) {
      this._seen.add('complete');
      this._appendCard({
        emoji: '🎓',
        title: this._i18n.training_complete ?? 'Training complete',
        message: s.run.story_summary ?? '',
        epoch: null,
        warning: false,
      });
    }

    if (!this._userScrolled) {
      this._el.scrollTop = this._el.scrollHeight;
    }
  }

  _appendCard({ emoji, title, message, epoch, warning }) {
    const card = document.createElement('div');
    card.className = `timeline-card${warning ? ' warning' : ''}`;
    card.innerHTML = `
      <span class="tc-emoji">${emoji}</span>
      <div class="tc-body">
        <div class="tc-title">${_esc(title)}</div>
        ${message ? `<div class="tc-msg">${_esc(message)}</div>` : ''}
      </div>
      ${epoch != null ? `<span class="tc-epoch">ep ${epoch}</span>` : ''}
    `;
    this._el.appendChild(card);
  }
}

/** @param {string} s */
function _esc(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
