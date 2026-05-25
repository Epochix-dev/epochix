/**
 * LearningMeter.js — SVG liquid-fill confidence meter.
 *
 * Shows the primary metric value as a rising liquid column.
 * Uses CSS @property animated gradient for the shimmer effect.
 */

export class LearningMeter {
  /** @param {HTMLElement} container */
  constructor(container) {
    this._container = container;
    this._unsub = null;
    this._svgEl = null;
    this._fill = null;
    this._valueText = null;
    this._labelText = null;
    this._build();
  }

  /** @param {import('../store.js').AppState} store */
  mount(store) {
    this._unsub = store.subscribe((s) => {
      const v = s.currentFrame?.primary_metric_value ?? 0;
      const conf = s.currentFrame?.confidence ?? 0;
      this._update(v, conf);
    });
    const s = store.get();
    this._update(
      s.currentFrame?.primary_metric_value ?? 0,
      s.currentFrame?.confidence ?? 0,
    );
  }

  unmount() {
    if (this._unsub) this._unsub();
  }

  // ── internal ──────────────────────────────────────────────────────────────

  _build() {
    const W = 80, H = 180, R = 12;
    const svgNS = 'http://www.w3.org/2000/svg';

    const svg = document.createElementNS(svgNS, 'svg');
    svg.setAttribute('viewBox', `0 0 ${W} ${H + 24}`);
    svg.style.width  = '100%';
    svg.style.height = '100%';
    svg.style.maxWidth = '100px';
    svg.style.margin = '0 auto';
    svg.style.display = 'block';

    // Define clip path
    const defs = document.createElementNS(svgNS, 'defs');
    const clip = document.createElementNS(svgNS, 'clipPath');
    clip.setAttribute('id', 'meter-clip');
    const clipRect = document.createElementNS(svgNS, 'rect');
    clipRect.setAttribute('x', '4');
    clipRect.setAttribute('y', '4');
    clipRect.setAttribute('width', W - 8);
    clipRect.setAttribute('height', H - 8);
    clipRect.setAttribute('rx', R);
    clip.appendChild(clipRect);
    defs.appendChild(clip);
    svg.appendChild(defs);

    // Background tube
    const bg = document.createElementNS(svgNS, 'rect');
    bg.setAttribute('x', '4');
    bg.setAttribute('y', '4');
    bg.setAttribute('width', W - 8);
    bg.setAttribute('height', H - 8);
    bg.setAttribute('rx', R);
    bg.setAttribute('fill', 'currentColor');
    bg.setAttribute('opacity', '0.06');
    svg.appendChild(bg);

    // Tube border
    const border = document.createElementNS(svgNS, 'rect');
    border.setAttribute('x', '4');
    border.setAttribute('y', '4');
    border.setAttribute('width', W - 8);
    border.setAttribute('height', H - 8);
    border.setAttribute('rx', R);
    border.setAttribute('fill', 'none');
    border.setAttribute('stroke', 'currentColor');
    border.setAttribute('stroke-opacity', '0.12');
    border.setAttribute('stroke-width', '1');
    svg.appendChild(border);

    // Fill rect (clipped)
    const fillRect = document.createElementNS(svgNS, 'rect');
    fillRect.setAttribute('x', '4');
    fillRect.setAttribute('y', H - 8);  // starts at bottom
    fillRect.setAttribute('width', W - 8);
    fillRect.setAttribute('height', '0');
    fillRect.setAttribute('clip-path', 'url(#meter-clip)');
    fillRect.style.transition = 'y 800ms cubic-bezier(.4,0,.2,1), height 800ms cubic-bezier(.4,0,.2,1)';
    svg.appendChild(fillRect);
    this._fill = fillRect;

    // Value text
    const vt = document.createElementNS(svgNS, 'text');
    vt.setAttribute('x', W / 2);
    vt.setAttribute('y', H + 16);
    vt.setAttribute('text-anchor', 'middle');
    vt.setAttribute('font-size', '13');
    vt.setAttribute('font-weight', '600');
    vt.setAttribute('fill', 'currentColor');
    svg.appendChild(vt);
    this._valueText = vt;

    // Tick marks
    [0.25, 0.5, 0.75].forEach((pct) => {
      const ty = 4 + (H - 8) * (1 - pct);
      const tick = document.createElementNS(svgNS, 'line');
      tick.setAttribute('x1', '4');
      tick.setAttribute('y1', ty);
      tick.setAttribute('x2', '12');
      tick.setAttribute('y2', ty);
      tick.setAttribute('stroke', 'currentColor');
      tick.setAttribute('stroke-opacity', '0.18');
      tick.setAttribute('stroke-width', '1');
      svg.appendChild(tick);
    });

    this._svgEl = svg;
    this._container.appendChild(svg);
    this._W = W;
    this._H = H;
  }

  _update(value, confidence) {
    const pct  = Math.max(0, Math.min(1, value));
    const H    = this._H;
    const fillH = (H - 8) * pct;
    const fillY = 4 + (H - 8) - fillH;

    // Color by value (green-to-blue gradient)
    const hue = 140 + (1 - pct) * 80; // 220 (blue) → 140 (green)
    const col = `hsl(${hue}, 70%, 55%)`;

    this._fill.setAttribute('y', fillY);
    this._fill.setAttribute('height', fillH);
    this._fill.setAttribute('fill', col);
    this._fill.setAttribute('fill-opacity', '0.7');

    this._valueText.textContent = `${(pct * 100).toFixed(1)}%`;
    this._valueText.setAttribute('fill', col);
  }
}
