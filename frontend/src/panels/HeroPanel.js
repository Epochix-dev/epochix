/**
 * HeroPanel.js — Brain canvas + confidence overlay.
 *
 * Owns the BrainCanvas and (optionally) a ParticleField background.
 */

import { BrainCanvas } from '../visualizations/BrainCanvas.js';

export class HeroPanel {
  /** @param {import('../store.js').AppState} store */
  constructor(store) {
    this._store   = store;
    this._brain   = null;
    this._mounted = false;
    this._summaryUnsub = null;
  }

  mount() {
    if (this._mounted) return;
    this._mounted = true;

    const canvas = document.getElementById('brain-canvas');
    if (!canvas) return;

    this._brain = new BrainCanvas(canvas);
    this._brain.start(this._store);

    // Interactive depth / gradient toggles
    const controls = document.getElementById('brain-controls');
    if (controls) {
      this._onControlsClick = (e) => {
        const btn = e.target.closest('.brain-toggle');
        if (!btn || !this._brain) return;
        const which = btn.dataset.toggle;
        let on = true;
        if (which === 'depth') on = this._brain.toggleDepth();
        else if (which === 'grad') on = this._brain.toggleGradient();
        btn.classList.toggle('is-on', on);
      };
      controls.addEventListener('click', this._onControlsClick);
      this._controls = controls;
    }

    // Architecture summary chip (HTML overlay, top-right)
    const summary = document.getElementById('brain-summary');
    if (summary) {
      this._summaryUnsub = this._store.subscribe((s) => _renderSummary(summary, s));
      _renderSummary(summary, this._store.get());
    }
  }

  unmount() {
    if (this._controls && this._onControlsClick) {
      this._controls.removeEventListener('click', this._onControlsClick);
    }
    if (this._summaryUnsub) this._summaryUnsub();
    if (this._brain) {
      this._brain.stop();
      this._brain = null;
    }
    this._mounted = false;
  }
}

/** Render the architecture summary chip from store state. */
function _renderSummary(el, s) {
  const arch = s.architecture;
  if (!arch?.length) { el.hidden = true; return; }
  const total = arch.reduce((sum, l) => sum + (l.params ?? 0), 0);
  const paramStr = total >= 1e6 ? `${(total / 1e6).toFixed(1)}M`
                 : total >= 1e3 ? `${(total / 1e3).toFixed(1)}K`
                 : String(total);
  // Collapse adjacent runs of the same layer type so a YOLO backbone reads
  // as "Conv ×4 + C2f ×3 + SPPF + Upsample" instead of an unreadable train
  // of "Conv + Conv + C2f + Conv + C2f + Conv + C2f + Conv + SPPF + …".
  const names = _compactLayerSequence(arch);
  const sig = `${names}|${paramStr}`;
  if (el.dataset.sig === sig) return;     // avoid needless DOM churn
  el.dataset.sig = sig;
  el.hidden = false;
  el.innerHTML = `
    <span class="bs-name" title="${_esc(names)}">${_esc(names)}</span>
    <span class="bs-meta">${arch.length} layer${arch.length !== 1 ? 's' : ''} · ${paramStr} params</span>`;
}

/** Collapse adjacent runs of identical layer_type into "Type ×N". */
function _compactLayerSequence(arch) {
  if (!arch.length) return '';
  const labels = arch.map((l) => l.layer_type ?? l.name ?? '?');
  const out = [];
  let prev = labels[0];
  let count = 1;
  for (let i = 1; i < labels.length; i++) {
    if (labels[i] === prev) {
      count += 1;
    } else {
      out.push(count > 1 ? `${prev} ×${count}` : prev);
      prev = labels[i];
      count = 1;
    }
  }
  out.push(count > 1 ? `${prev} ×${count}` : prev);
  return out.join(' + ');
}

function _esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
