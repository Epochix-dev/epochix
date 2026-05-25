/**
 * SkillsPanel.js — skill radar + confidence bars + learning meter.
 */

import { SkillRadar }      from '../visualizations/SkillRadar.js';
import { LearningMeter }   from '../visualizations/LearningMeter.js';
import { ConfidenceBars }  from '../visualizations/ConfidenceBars.js';

export class SkillsPanel {
  /** @param {import('../store.js').AppState} store */
  constructor(store) {
    this._store  = store;
    this._radar  = null;
    this._meter  = null;
    this._bars   = null;
  }

  mount() {
    // Skill radar — container is the #skill-radar div itself
    const radarEl = document.getElementById('skill-radar');
    if (radarEl) {
      this._radar = new SkillRadar(radarEl);
      this._radar.mount(this._store);
    }

    // Learning meter
    const meterEl = document.getElementById('learning-meter');
    if (meterEl) {
      this._meter = new LearningMeter(meterEl);
      this._meter.mount(this._store);
    }

    // Confidence bars
    const barsEl = document.getElementById('confidence-bars');
    if (barsEl) {
      this._bars = new ConfidenceBars(barsEl);
      this._bars.mount(this._store);
    }
  }

  unmount() {
    if (this._radar) this._radar.unmount();
    if (this._meter) this._meter.unmount();
    if (this._bars)  this._bars.unmount();
  }
}
