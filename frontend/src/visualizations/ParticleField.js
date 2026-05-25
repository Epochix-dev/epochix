/**
 * ParticleField.js — ambient background particle drift.
 *
 * A gentle field of drifting dots that speeds up with confidence.
 * Used as a subtle background layer inside panels.
 */

export class ParticleField {
  /**
   * @param {HTMLCanvasElement} canvas
   * @param {{ count?: number, color?: string }} [opts]
   */
  constructor(canvas, opts = {}) {
    this._canvas  = canvas;
    this._ctx     = canvas.getContext('2d');
    this._count   = opts.count ?? 40;
    this._color   = opts.color ?? '#7c6dff';
    this._particles = [];
    this._speed   = 0.3;
    this._raf     = null;
    this._unsub   = null;
    this._t       = 0;
  }

  /** @param {import('../store.js').AppState} store */
  mount(store) {
    this._unsub = store.subscribe((s) => {
      this._speed = 0.2 + (s.currentFrame?.confidence ?? 0) * 0.8;
    });
    this._resize();
    window.addEventListener('resize', () => this._resize());
    this._buildParticles();
    this._loop();
  }

  unmount() {
    if (this._unsub) this._unsub();
    cancelAnimationFrame(this._raf);
  }

  // ── internal ──────────────────────────────────────────────────────────────

  _resize() {
    const p   = this._canvas.parentElement;
    if (!p) return;
    const dpr = window.devicePixelRatio || 1;
    this._canvas.width  = p.clientWidth  * dpr;
    this._canvas.height = p.clientHeight * dpr;
    this._canvas.style.width  = `${p.clientWidth}px`;
    this._canvas.style.height = `${p.clientHeight}px`;
    this._ctx.scale(dpr, dpr);
    this._w = p.clientWidth;
    this._h = p.clientHeight;
    this._buildParticles();
  }

  _buildParticles() {
    const w = this._w || 400;
    const h = this._h || 300;
    this._particles = Array.from({ length: this._count }, () => ({
      x:  Math.random() * w,
      y:  Math.random() * h,
      vx: (Math.random() - 0.5) * 0.4,
      vy: (Math.random() - 0.5) * 0.4,
      r:  0.6 + Math.random() * 1.4,
      o:  0.1 + Math.random() * 0.3,
    }));
  }

  _loop() {
    this._raf = requestAnimationFrame(() => {
      this._draw();
      this._loop();
    });
  }

  _draw() {
    const ctx = this._ctx;
    const w   = this._w || this._canvas.width;
    const h   = this._h || this._canvas.height;
    const spd = this._speed;

    ctx.clearRect(0, 0, w, h);

    for (const p of this._particles) {
      p.x = (p.x + p.vx * spd + w) % w;
      p.y = (p.y + p.vy * spd + h) % h;

      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = `${this._color}${Math.round(p.o * 255).toString(16).padStart(2, '0')}`;
      ctx.fill();
    }
  }
}
