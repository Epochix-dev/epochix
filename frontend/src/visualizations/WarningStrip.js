/**
 * WarningStrip.js — show the warnings the engine already produces.
 *
 * The story engine emits a Warning for overfitting, a plateau, divergence and a
 * learning-rate drop. `sse-client` receives them, `store.warnings` holds them —
 * and nothing rendered them, so a run that was diverging computed the warning,
 * transmitted it, stored it, and told the user nothing.
 *
 * Deliberately quiet: it occupies no space when there is nothing wrong, because
 * a panel that is always present teaches people to stop reading it.
 */

import { escapeHtml } from '../escape.js';

export class WarningStrip {
  /** @param {HTMLElement} el */
  constructor(el) {
    this._el = el;
    this._unsub = null;
    this._last = '';
  }

  /** @param {{subscribe: Function, get: Function}} store */
  mount(store) {
    this._unsub = store.subscribe((s) => this.render(s.warnings ?? []));
    this.render(store.get().warnings ?? []);
  }

  /** @param {string[]} warnings */
  render(warnings) {
    if (!this._el) return;
    // Same list, same DOM: re-rendering on every frame would restart the CSS
    // transition and make a steady warning flicker.
    const key = warnings.join('\u0000');
    if (key === this._last) return;
    this._last = key;

    if (warnings.length === 0) {
      this._el.innerHTML = '';
      this._el.hidden = true;
      return;
    }
    this._el.hidden = false;
    this._el.innerHTML = warnings
      .map((w) => `<div class="warn-item"><span class="warn-ico">⚠</span>${escapeHtml(String(w))}</div>`)
      .join('');
  }

  destroy() {
    if (this._unsub) this._unsub();
    this._unsub = null;
  }
}
