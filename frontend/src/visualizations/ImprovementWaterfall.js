/**
 * ImprovementWaterfall.js — Canvas particle burst on metric improvement.
 *
 * Each epoch where the primary metric improves fires a burst of particles
 * that float upward and fade. "Improves" respects the metric direction —
 * accuracy rising vs. MAE/RMSE/loss falling — so it never celebrates a
 * regression on a lower-is-better run. Runs its own rAF loop.
 */

import { LOWER_IS_BETTER } from '../viz-util.js';

export class ImprovementWaterfall {
  /** @param {HTMLCanvasElement} canvas */
  constructor(canvas) {
    this._canvas = canvas;
    this._ctx = canvas.getContext('2d');
    this._particles = [];
    this._lastValue = null;
    this._raf = null;
    this._unsub = null;
    this._running = false;
  }

  /** @param {import('../store.js').AppState} store */
  mount(store) {
    this._unsub = store.subscribe((s) => {
      const v = s.currentFrame?.primary_metric_value ?? null;
      const lowerBetter = LOWER_IS_BETTER.has(s.run?.primary_metric);
      if (v !== null && this._lastValue !== null) {
        const improved = lowerBetter ? v < this._lastValue : v > this._lastValue;
        if (improved) this._burst(Math.abs(v - this._lastValue));
      }
      this._lastValue = v;
    });
    this._resize();
    this._start();
  }

  unmount() {
    if (this._unsub) this._unsub();
    this._stop();
  }

  // ── internal ──────────────────────────────────────────────────────────────

  _resize() {
    const el = this._canvas;
    const p  = el.parentElement;
    if (!p) return;
    const dpr = window.devicePixelRatio || 1;
    el.width  = p.clientWidth  * dpr;
    el.height = p.clientHeight * dpr;
    el.style.width  = `${p.clientWidth}px`;
    el.style.height = `${p.clientHeight}px`;
    this._ctx.scale(dpr, dpr);
    this._w = p.clientWidth;
    this._h = p.clientHeight;
  }

  /** @param {number} delta - improvement magnitude */
  _burst(delta) {
    const n = Math.min(40, Math.max(6, Math.round(delta * 100)));
    const w = this._w || 200;
    const h = this._h || 100;
    for (let i = 0; i < n; i++) {
      this._particles.push({
        x:    w * 0.1 + Math.random() * w * 0.8,
        y:    h * 0.8 + Math.random() * h * 0.1,
        vx:   (Math.random() - 0.5) * 2,
        vy:   -(1.5 + Math.random() * 3),
        r:    1.5 + Math.random() * 2.5,
        life: 1.0,
        hue:  140 + Math.random() * 80,
      });
    }
    if (!this._running) this._start();
  }

  _start() {
    this._running = true;
    const loop = () => {
      this._draw();
      if (this._particles.length > 0 || this._running) {
        this._raf = requestAnimationFrame(loop);
      }
    };
    this._raf = requestAnimationFrame(loop);
  }

  _stop() {
    this._running = false;
    cancelAnimationFrame(this._raf);
  }

  _draw() {
    const ctx = this._ctx;
    const w   = this._w || this._canvas.width;
    const h   = this._h || this._canvas.height;

    ctx.clearRect(0, 0, w, h);

    this._particles = this._particles.filter((p) => p.life > 0.01);

    for (const p of this._particles) {
      p.x  += p.vx;
      p.y  += p.vy;
      p.vy += 0.04; // gravity
      p.life -= 0.018;

      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r * p.life, 0, Math.PI * 2);
      ctx.fillStyle = `hsla(${p.hue}, 70%, 60%, ${p.life * 0.8})`;
      ctx.fill();
    }
  }
}
