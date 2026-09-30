/**
 * WarningStrip.js — show the warnings the engine already produces.
 *
 * The story engine emits a Warning for overfitting, a plateau, divergence and a
 * learning-rate drop. `sse-client` receives them, `store.warnings` holds them —
 * and nothing rendered them, so a run that was diverging computed the warning,
 * transmitted it, stored it, and told the user nothing.
 *
 * Deliberately quiet: it occupies no space when there is nothing wrong, because
 * a panel that is always present teaches people to stop reading it. A
 * learning-rate drop is not something wrong — a ResNet-18's planned one-cycle
 * decay filled the strip with three amber warnings — so it is left to the
 * learning-rate chart and the report's history.
 */

/** Warning kinds that are information, not a problem. */
const NOT_A_PROBLEM = new Set(['lr_drop']);

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
    this._unsub = store.subscribe((s) => this.render(problems(s)));
    this.render(problems(store.get()));
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

/** @param {{warnings?: string[], warningKinds?: Object<string,string>}} s */
function problems(s) {
  const kinds = s.warningKinds ?? {};
  return (s.warnings ?? []).filter((m) => !NOT_A_PROBLEM.has(kinds[m]));
}
