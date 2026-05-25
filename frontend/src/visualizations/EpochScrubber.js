/**
 * EpochScrubber.js — range input for scrubbing through training epochs.
 *
 * When dragged, calls scrubTo(idx) on the store. The "latest" button
 * releases the scrub lock and snaps back to live.
 */

import { scrubTo } from '../store.js';

export class EpochScrubber {
  /** @param {HTMLElement} container */
  constructor(container) {
    this._el = container;
    this._unsub = null;
    this._input = null;
    this._label = null;
    this._totalFrames = 0;
    this._build();
  }

  /** @param {import('../store.js').AppState} store */
  mount(store) {
    this._unsub = store.subscribe((s) => {
      const n = s.frames.length;
      if (n !== this._totalFrames) {
        this._totalFrames = n;
        this._input.max = Math.max(0, n - 1);
        if (s.scrubEpoch === -1) {
          this._input.value = this._input.max;
        }
        this._updateLabel(s);
      }
    });
  }

  unmount() {
    if (this._unsub) this._unsub();
  }

  // ── internal ──────────────────────────────────────────────────────────────

  _build() {
    this._el.innerHTML = `
      <div class="scrubber-label">
        <span id="scrubber-epoch-label">Epoch —</span>
        <button class="scrubber-live-btn" id="scrubber-live-btn" style="display:none">↩ Latest</button>
      </div>
      <input type="range" id="epoch-scrubber" min="0" max="0" value="0" step="1" />
    `;

    this._input = this._el.querySelector('#epoch-scrubber');
    this._label = this._el.querySelector('#scrubber-epoch-label');
    this._liveBtn = this._el.querySelector('#scrubber-live-btn');

    this._input.addEventListener('input', () => {
      const idx = parseInt(this._input.value, 10);
      scrubTo(idx);
      this._liveBtn.style.display = '';
    });

    this._liveBtn.addEventListener('click', () => {
      scrubTo(-1);
      this._input.value = this._input.max;
      this._liveBtn.style.display = 'none';
    });
  }

  _updateLabel(s) {
    const frame = s.currentFrame;
    if (frame?.epoch != null) {
      this._label.textContent = `Epoch ${frame.epoch}`;
    } else if (this._totalFrames > 0) {
      this._label.textContent = `Frame ${this._totalFrames}`;
    } else {
      this._label.textContent = 'Epoch —';
    }
  }
}

// Inject scrubber styles once
if (!document.getElementById('scrubber-styles')) {
  const s = document.createElement('style');
  s.id = 'scrubber-styles';
  s.textContent = `
    .scrubber-live-btn {
      background: none;
      border: 1px solid var(--accent-primary);
      color: var(--accent-primary);
      border-radius: var(--radius-sm);
      padding: 2px 8px;
      font-size: 11px;
      cursor: pointer;
    }
    .scrubber-live-btn:hover {
      background: var(--accent-glow);
    }
  `;
  document.head.appendChild(s);
}
