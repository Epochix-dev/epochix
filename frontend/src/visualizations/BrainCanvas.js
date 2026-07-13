/**
 * BrainCanvas.js — architecture-aware layered neural-network visualization.
 *
 * Dual audience:
 *  Non-technical  — zones labeled in plain English; progress ring; particles
 *  Technical      — real layer names + types; param-proportional widths;
 *                   overfitting halo; architecture summary card; gradient flow
 *
 * Feature list
 * ────────────
 * ① Architecture-aware layout  — if run.config.architecture is present the
 *     canvas builds columns from the actual layers; otherwise it renders an
 *     honest "no architecture" message rather than inventing a topology.
 * ② Dual zone labels            — technical (ENCODER) above + plain English
 *     ("Feature extractor") below each column.
 * ③ Param-proportional widths   — column width ∝ log10(params).
 * ④ Accuracy progress ring      — arc on the output zone fills with accuracy.
 * ⑤ Architecture summary card   — top-right overlay: model name + param count.
 * ⑥ Overfitting warning halo    — output zone pulses red when loss diverges.
 * ⑦ Particle zone-label flash   — micro-label bursts when a signal crosses a
 *     zone boundary.
 * ⑧ Recurrent self-loop motifs  — LSTM/GRU/RNN zones grow memory-feedback
 *     loops with an orbiting pulse ("remembers context").
 * ⑨ Attention beam motifs       — attention/transformer zones render a
 *     shimmering all-to-all beam web ("reads full context").
 * ⑩ Pseudo-3D depth             — zones drawn as isometric slabs (Canvas 2D,
 *     no WebGL — keeps the bundle small).
 * ⑪ Gradient-flow (backprop)    — per-layer ∇ bars from REAL captured gradient
 *     magnitudes (backward hooks), plus a warm particle stream output→input.
 *     The bars appear only when gradients are captured; otherwise they're hidden
 *     (the particle stream is ambient animation only, not a measurement).
 *
 * Honesty note
 * ────────────
 * The layout (layer count, types, param counts, order) is REAL — built from the
 * model's architecture. Individual neuron positions and the per-edge signed
 * weights are generated for the diagram (like TF-Playground's generic network).
 * These dynamics are tied to real training data:
 *  Node brightness / dead nodes → REAL captured per-layer activation magnitude
 *     and zero-unit fraction, when LiveReporter(capture_activations=True) is on
 *     (store.activations); otherwise scaled by val_accuracy as a schematic.
 *  Gradient ∇ bars          → REAL captured mean |gradient| per layer (backward
 *     hooks), normalised across layers so the heights show the model's actual
 *     gradient distribution. Hidden entirely when no gradients are captured —
 *     never an invented vanishing-gradient curve.
 *  Particle speed/spawn     → training advancement (ambient animation)
 *  Overfitting halo         → real train/val gap (val_loss − train_loss)
 * Edge colour/thickness stay schematic (illustrative +/− connections) — weights
 * aren't cheaply forward-pass observable — and the legend says so.
 */

// ── zone colour palette ───────────────────────────────────────────────────────
const ZONE_COLORS = {
  input:      '#34d399',  // emerald  – input
  output:     '#f472b6',  // pink     – output / decision
  conv:       '#818cf8',  // indigo   – spatial conv
  dense:      '#fbbf24',  // amber    – FC / decision
  recurrent:  '#22d3ee',  // cyan     – memory
  attention:  '#a78bfa',  // violet   – attention / transformer
  norm:       '#6b7280',  // grey     – normalisation / dropout
  generic:    '#60a5fa',  // blue     – unknown
};

// Particle zone-crossing micro-labels per visual_type
const ZONE_FLASH_LABELS = {
  input:     'input data',
  conv:      'features…',
  recurrent: 'remembering…',
  attention: 'focusing…',
  dense:     'deciding…',
  norm:      'stabilising…',
  output:    'classified!',
  generic:   'processing…',
};

// Depth (isometric) offsets in px — large enough that the 3D extrusion reads
// clearly. Front face sits forward; top + right faces give the slab volume.
const DEPTH_DX = 24;
const DEPTH_DY = 22;
const GRAD_COLOR = '#fb923c'; // warm orange for gradient/backprop stream
const EDGE_POS = '#5b8def';   // positive weight (blue) — TF-Playground style
const EDGE_NEG = '#fb923c';   // negative weight (orange)

// Vertical layout lanes (px)
const TOP_STRIP = 24;   // reserved top band for HTML overlays (toggles/summary)

// ── helpers ───────────────────────────────────────────────────────────────────

/** @param {string} hex  @param {number} alpha */
function hexAlpha(hex, alpha) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${Math.max(0, Math.min(1, alpha)).toFixed(3)})`;
}

/**
 * Column pixel-width from param count using a log scale, clamped to [40, 150].
 * @param {number} params
 */
function _paramWidth(params) {
  if (!params) return 60;
  const w = 16 * Math.log10(params + 1);
  return Math.max(40, Math.min(150, w));
}


// ── main class ────────────────────────────────────────────────────────────────

export class BrainCanvas {
  /** @param {HTMLCanvasElement} canvas */
  constructor(canvas) {
    this._canvas = canvas;
    this._ctx    = canvas.getContext('2d');
    this._raf    = null;
    this._t      = 0;

    // Training signals
    this._phase     = 'awakening';
    this._valAcc    = 0.1;
    this._trainLoss = 1.0;
    this._progress  = 0.05;
    this._overfit   = false;   // val_acc diverging from train_acc

    // Smooth targets
    this._targetValAcc    = 0.1;
    this._targetTrainLoss = 1.0;

    // Gradient-flow signal (backprop intensity proxy)
    this._gradIntensity = 0.4;  // smoothed overall magnitude
    this._gradSpike     = 0;    // transient burst on metric jumps
    this._prevTargetAcc = null;

    // Particles
    this._particles     = [];
    this._gradParticles = [];   // backward-flowing gradient stream

    // Zone / node layout
    this._zones    = [];  // [{id, color, x, width, nodes[], techLabel, plainLabel, visualType, params, gradMag}]
    this._edges    = [];  // [{a, b, fromZoneIdx}]

    // Architecture (from store)
    this._architecture = null;
    this._noArch = false;

    // Real per-layer activations (from store; null = schematic fallback).
    // _actMax tracks a per-layer running max for [0,1] normalisation so
    // brightness is comparable across layers of very different scales.
    this._activations = null;
    this._actMax = {};
    this._hadRealActivations = false;
    this._hasRealGrad = false;  // per-layer ∇ bars drawn only from captured grads

    // Render toggles (interactive via overlay buttons)
    this._depth3d   = true;
    this._showGrad  = true;

    this._store    = null;
    this._unsub    = null;
    this._resizeObs = null;
    this._cw = 400;
    this._ch = 300;

    // Active flash labels on particles
    this._flashes = []; // [{x, y, label, alpha}]

    // Hover-to-enlarge state
    this._hoverNode = null;
    this._tooltip   = null;
    this._onMove    = null;
    this._onLeave   = null;
  }

  start(store) {
    this._store = store;
    this._unsub = store.subscribe((s) => this._onState(s));
    this._onState(store.get());
    this._resizeObs = new ResizeObserver(() => this._resize());
    this._resizeObs.observe(this._canvas.parentElement);
    this._resize();

    // Hover tooltip (enlarge a neuron + show its layer details)
    const wrap = this._canvas.parentElement;
    if (wrap) {
      const tip = document.createElement('div');
      tip.className = 'brain-tooltip';
      tip.style.display = 'none';
      wrap.appendChild(tip);
      this._tooltip = tip;
      this._onMove = (e) => {
        const rect = this._canvas.getBoundingClientRect();
        this._handleHover(e.clientX - rect.left, e.clientY - rect.top);
      };
      this._onLeave = () => {
        this._hoverNode = null;
        if (this._tooltip) this._tooltip.style.display = 'none';
      };
      this._canvas.addEventListener('mousemove', this._onMove);
      this._canvas.addEventListener('mouseleave', this._onLeave);
    }

    this._loop();
  }

  stop() {
    cancelAnimationFrame(this._raf);
    if (this._unsub) this._unsub();
    if (this._resizeObs) this._resizeObs.disconnect();
    if (this._onMove)  this._canvas.removeEventListener('mousemove', this._onMove);
    if (this._onLeave) this._canvas.removeEventListener('mouseleave', this._onLeave);
    if (this._tooltip) this._tooltip.remove();
  }

  /** Find the neuron under the cursor → enlarge it + show a details tooltip. */
  _handleHover(px, py) {
    let best = null, bestD = Infinity, bestZone = null;
    for (const zone of this._zones) {
      for (const n of zone.nodes) {
        const d = (n.x - px) ** 2 + (n.y - py) ** 2;
        if (d < bestD) { bestD = d; best = n; bestZone = zone; }
      }
    }
    const r = best ? 5 + best.activation * 5 : 0;
    if (best && bestD <= (r + 9) ** 2 && this._tooltip) {
      this._hoverNode = best;
      const paramStr = bestZone.paramsStr
        ?? (bestZone.params ? _fmtParams(bestZone.params) : null);
      // Activity is a layer-level reading of the real training signal (val
      // accuracy), not per-node noise — so every neuron in a layer reads the
      // same, and the number reflects actual data rather than animation.
      const sig = this._valAcc;
      const activity = sig >= 0.66 ? 'High' : sig >= 0.33 ? 'Medium' : 'Low';
      this._tooltip.innerHTML = `
        <div class="bt-title">${_escTip(bestZone.layerType ?? bestZone.techLabel)}</div>
        <div class="bt-sub">${_escTip(bestZone.plainLabel)}</div>
        ${paramStr ? `<div class="bt-row"><span>params</span><b>${_escTip(paramStr)}</b></div>` : ''}
        <div class="bt-row"><span>activity</span><b>${activity}</b></div>`;
      this._tooltip.style.display = 'block';
      this._tooltip.style.left = `${Math.min(px + 14, this._cw - 130)}px`;
      this._tooltip.style.top  = `${Math.max(4, py - 10)}px`;
    } else {
      this._hoverNode = null;
      if (this._tooltip) this._tooltip.style.display = 'none';
    }
  }

  /** Public toggles for the panel overlay buttons. */
  setDepth(on)    { this._depth3d  = !!on; }
  setGradient(on) { this._showGrad = !!on; }
  toggleDepth()    { this._depth3d  = !this._depth3d;  return this._depth3d; }
  toggleGradient() { this._showGrad = !this._showGrad; return this._showGrad; }

  // ── private ──────────────────────────────────────────────────────────────

  _onState(s) {
    const f = s.currentFrame;

    // Rebuild network topology when architecture or phase changes
    const newArch  = s.architecture ?? null;
    const newPhase = f?.phase ?? 'awakening';
    if (newArch !== this._architecture || newPhase !== this._phase) {
      this._architecture = newArch;
      this._phase        = newPhase;
      this._buildNetwork();
    }

    // Real per-layer activations (LiveReporter capture_activations=True). When
    // absent the node animation stays schematic and the legend says so.
    this._activations = s.activations ?? null;
    const hasReal = !!(this._activations && Object.keys(this._activations).length);
    if (hasReal !== this._hadRealActivations) {
      this._hadRealActivations = hasReal;
      const hint = document.getElementById('brain-wlegend-hint');
      if (hint) {
        // Nodes become real when captured; edges (weights) are never forward-pass
        // observable cheaply, so they stay schematic and the legend keeps saying so.
        hint.textContent = hasReal
          ? 'nodes: live activations · edges: schematic'
          : 'schematic · illustrative, not measured weights';
      }
    }

    if (!f) return;
    const acc = Math.max(0.05, Math.min(1, f.primary_metric_value ?? 0.1));

    // Gradient spike when the primary metric jumps between frames
    if (this._prevTargetAcc !== null) {
      this._gradSpike = Math.min(1, this._gradSpike + Math.abs(acc - this._prevTargetAcc) * 6);
    }
    this._prevTargetAcc = acc;

    this._targetValAcc    = acc;
    this._targetTrainLoss = Math.max(0.05, Math.min(1, f.skill_dimensions?.Fitting ?? 0.5));
    this._progress        = Math.max(0.05, Math.min(1, f.progress ?? 0.1));

    // Overfitting: the model fits training data well but validation lags —
    // a REAL train/val gap from skill dimensions (Fitting≈1−train_loss,
    // Generalisation≈1−val_loss), not a progress proxy.
    const fit = f.skill_dimensions?.Fitting;
    const gen = f.skill_dimensions?.Generalisation;
    this._overfit =
      Number.isFinite(fit) && Number.isFinite(gen) && fit > 0.5 && (fit - gen) > 0.15;
  }

  _resize() {
    const parent = this._canvas.parentElement;
    if (!parent) return;
    const dpr = window.devicePixelRatio || 1;
    const w   = parent.clientWidth;
    const h   = parent.clientHeight || 300;
    // A ResizeObserver can fire mid-reflow (e.g. a flex column collapsing to a
    // narrow layout) while the parent momentarily reports 0 width. Sizing the
    // canvas to 0 then would leave the network view permanently blank, so
    // retry on the next frame instead of locking in a zero-width buffer.
    if (w <= 0) {
      requestAnimationFrame(() => this._resize());
      return;
    }
    this._canvas.width  = w * dpr;
    this._canvas.height = h * dpr;
    this._canvas.style.width  = `${w}px`;
    this._canvas.style.height = `${h}px`;
    this._ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this._cw = w;
    this._ch = h;
    this._buildNetwork();
  }

  /**
   * Build zone+node layout from real architecture data, or mark _noArch when
   * none is available (the draw pass then shows an honest empty state).
   */
  _buildNetwork() {
    const w = this._cw;
    const h = this._ch;

    const arch = this._architecture;
    // Top strip is reserved for HTML overlays; both zone labels live at the
    // bottom, so PAD_BOT carries the gradient bar + two label lines.
    const PAD_TOP = 46, PAD_BOT = 62, PAD_H = 30;

    if (arch && arch.length > 0) {
      this._noArch = false;
      // ── Architecture-aware layout ────────────────────────────────────────
      // Zones: [INPUT] + arch layers + [OUTPUT]
      const zoneDefs = [
        { id: 'input',  techLabel: 'INPUT',  plainLabel: 'Raw data',   visualType: 'input',  params: 0, name: 'input' },
        ...arch.map((l) => ({
          id: l.name, techLabel: l.tech_label, plainLabel: l.plain_label,
          visualType: l.visual_type, params: l.params, paramsStr: l.params_str,
          name: l.name, layerType: l.layer_type,
        })),
        { id: 'output', techLabel: 'OUTPUT', plainLabel: 'Decision',   visualType: 'output', params: 0, name: 'output' },
      ];

      // Compute widths
      const fixedW  = 52;   // input + output fixed width
      const midW    = w - PAD_H * 2 - fixedW * 2 - DEPTH_DX;
      const midLayers = zoneDefs.slice(1, -1);

      // Sum of log-scale weights for middle layers
      const rawWeights = midLayers.map((z) => _paramWidth(z.params));
      const totalW = rawWeights.reduce((a, b) => a + b, 0) || 1;

      const widths = [
        fixedW,
        ...rawWeights.map((rw) => (rw / totalW) * midW),
        fixedW,
      ];

      // X centres
      let cursor = PAD_H;
      this._zones = zoneDefs.map((z, i) => {
        const zw   = widths[i];
        const cx   = cursor + zw / 2;
        cursor    += zw;
        return { ...z, x: cx, width: zw, nodes: [], gradMag: 0,
                 color: ZONE_COLORS[z.visualType] ?? ZONE_COLORS.generic };
      });

    } else {
      // ── No architecture available ────────────────────────────────────────
      // We do NOT invent one. The panel renders an honest "no architecture"
      // message (see _draw); the SDK caller can pass model=… to show the real
      // network, or the training log can include a model summary.
      this._noArch = true;
      this._zones = [];
      this._edges = [];
      this._particles = [];
      this._gradParticles = [];
      return;
    }

    // Build nodes per zone
    const nodeH = h - PAD_TOP - PAD_BOT;
    for (const zone of this._zones) {
      const count = _zoneNodeCount(zone);
      const yStep = nodeH / (count + 1);
      zone.nodes = Array.from({ length: count }, (_, ni) => ({
        x:          zone.x,
        y:          PAD_TOP + yStep * (ni + 1),
        activation: Math.random() * 0.4 + 0.3,
        dead:       false,
        phase:      Math.random() * Math.PI * 2,
        // Stable rank in [0,1): a real dead-fraction d marks the lowest-ranked
        // ~d of nodes as dead, so the count of dark nodes reads as the fraction.
        deadRank:   (ni + 0.5) / count,
      }));
    }

    // Fully connect adjacent zones
    this._edges = [];
    for (let zi = 0; zi < this._zones.length - 1; zi++) {
      for (const a of this._zones[zi].nodes) {
        for (const b of this._zones[zi + 1].nodes) {
          // Signed weight: magnitude → thickness, sign → colour (blue/orange).
          const mag = Math.random() * 0.9 + 0.1;
          this._edges.push({
            a, b, fromZoneIdx: zi,
            weight: Math.random() < 0.5 ? -mag : mag,
          });
        }
      }
    }

    this._particles     = [];
    this._gradParticles = [];
    this._flashes       = [];
  }

  _loop() {
    this._raf = requestAnimationFrame(() => {
      this._update();
      this._draw();
      this._loop();
    });
  }

  _update() {
    const dt = 0.016;
    this._t += dt;

    // Smooth interpolation toward targets
    this._valAcc    += (this._targetValAcc    - this._valAcc)    * 0.03;
    this._trainLoss += (this._targetTrainLoss - this._trainLoss) * 0.03;

    // ── Backprop animation liveliness (NOT a measurement) ───────────────────
    // Drives only the density/speed of the ambient backward particle stream —
    // more lively early, calmer near convergence. No quantitative claim.
    const gradTarget = Math.max(0.08, (1 - this._valAcc) * 0.9 + this._gradSpike * 0.6);
    this._gradIntensity += (gradTarget - this._gradIntensity) * 0.05;
    this._gradSpike      *= 0.94;

    // ── Per-layer gradient-magnitude bars: REAL captured values only ────────
    // mean |gradient| per layer from backward hooks (store.activations[l].grad),
    // normalised ACROSS layers at this step so the bar heights show the model's
    // actual gradient distribution (the real vanishing/exploding-gradient
    // signal). With no captured gradients (capture off / log-based run) there is
    // nothing real to show, so the bars are hidden rather than invented.
    const gacts = this._activations;
    const grads = this._zones.map((z) => (gacts ? gacts[z.name]?.grad : undefined));
    const gmax = Math.max(0, ...grads.filter((g) => Number.isFinite(g)));
    this._hasRealGrad = gmax > 0;
    for (let zi = 0; zi < this._zones.length; zi++) {
      const g = grads[zi];
      this._zones[zi].gradMag =
        this._hasRealGrad && Number.isFinite(g) ? Math.max(0, Math.min(1, g / gmax)) : 0;
    }

    // Update node activations. When real captured magnitudes are available for
    // a layer, the node level is the measured value (normalised per-layer to
    // [0,1]); we animate a gentle wobble around it so the panel still breathes
    // without inventing the level. Dead nodes reflect the real zero-unit
    // fraction. Layers with no capture (and the synthetic INPUT/OUTPUT zones)
    // keep the schematic animation.
    const acts = this._activations;
    for (const zone of this._zones) {
      const real = acts ? acts[zone.name] : null;
      let level = null, deadFrac = 0;
      if (real && Number.isFinite(real.mag)) {
        const mx = Math.max(this._actMax[zone.name] ?? 0, real.mag, 1e-9);
        this._actMax[zone.name] = mx;
        level    = Math.max(0.05, Math.min(1, real.mag / mx));
        deadFrac = Number.isFinite(real.dead) ? real.dead : 0;
      }
      for (const node of zone.nodes) {
        const t = this._t * (0.8 + node.phase * 0.3);
        if (level !== null) {
          node.dead       = node.deadRank < deadFrac;
          const wobble    = 0.06 * Math.sin(t + node.phase);
          node.activation = node.dead ? 0.05 : Math.max(0.05, Math.min(1, level + wobble));
        } else {
          const base      = this._valAcc * (0.5 + 0.5 * Math.sin(t + node.phase));
          node.dead       = this._targetTrainLoss < 0.15 && Math.random() < 0.001;
          node.activation = node.dead ? 0.05 : Math.max(0.05, Math.min(1, base));
        }
      }
    }

    // Spawn forward (inference) particles
    const rate = 0.3 + this._progress * 1.2;
    if (Math.random() < rate * dt && this._zones.length > 0) {
      const fromNode = this._zones[0].nodes[
        Math.floor(Math.random() * this._zones[0].nodes.length)
      ];
      const path = [fromNode];
      for (let zi = 1; zi < this._zones.length; zi++) {
        const z = this._zones[zi];
        path.push(z.nodes[Math.floor(Math.random() * z.nodes.length)]);
      }
      this._particles.push({
        path,
        t:           0,
        speed:       0.6 + this._progress * 1.5,
        alpha:       0.6 + this._valAcc * 0.4,
        lastZoneIdx: 0,
      });
    }

    // Spawn backward gradient particles (output → input) when enabled
    if (this._showGrad && this._zones.length > 1) {
      const gRate = this._gradIntensity * 2.4;
      if (Math.random() < gRate * dt) {
        const last = this._zones.length - 1;
        const fromNode = this._zones[last].nodes[
          Math.floor(Math.random() * this._zones[last].nodes.length)
        ];
        const path = [fromNode];
        for (let zi = last - 1; zi >= 0; zi--) {
          const z = this._zones[zi];
          path.push(z.nodes[Math.floor(Math.random() * z.nodes.length)]);
        }
        this._gradParticles.push({ path, t: 0, speed: 0.9 + this._gradIntensity });
      }
    }

    // Advance forward particles + detect zone crossings for flash labels
    this._particles = this._particles.filter((p) => {
      p.t += p.speed * dt;
      const zoneIdx = Math.floor(p.t);
      if (zoneIdx > p.lastZoneIdx && zoneIdx < this._zones.length) {
        const zone  = this._zones[zoneIdx];
        const label = ZONE_FLASH_LABELS[zone.visualType] ?? 'processing…';
        const a     = p.path[zoneIdx - 1];
        const b     = p.path[zoneIdx];
        const frac  = p.t - Math.floor(p.t);
        if (a && b) {
          this._flashes.push({
            x: a.x + (b.x - a.x) * frac,
            y: a.y + (b.y - a.y) * frac - 12,
            label,
            alpha: 0.85,
          });
        }
        p.lastZoneIdx = zoneIdx;
      }
      return p.t < p.path.length - 1;
    });

    // Advance backward gradient particles
    this._gradParticles = this._gradParticles.filter((p) => {
      p.t += p.speed * dt;
      return p.t < p.path.length - 1;
    });

    // Fade flash labels
    this._flashes = this._flashes.filter((f) => {
      f.alpha -= 0.012;
      return f.alpha > 0;
    });
  }

  _draw() {
    const ctx = this._ctx;
    const w   = this._cw;
    const h   = this._ch;
    ctx.clearRect(0, 0, w, h);

    if (this._zones.length === 0) {
      // Honest empty state — we never draw a made-up network.
      ctx.textAlign = 'center';
      ctx.fillStyle = 'rgba(255,255,255,0.42)';
      ctx.font = '12px DM Sans, sans-serif';
      ctx.fillText('No architecture to display', w / 2, h / 2 - 8);
      ctx.fillStyle = 'rgba(255,255,255,0.28)';
      ctx.font = '10px DM Sans, sans-serif';
      ctx.fillText(
        'Pass model=… to LiveReporter, or include a model summary in the log',
        w / 2,
        h / 2 + 12,
      );
      return;
    }

    // ── Zone slabs (pseudo-3D) or flat bands ──────────────────────────────
    const slabTop = TOP_STRIP;
    const slabH   = h - TOP_STRIP - 6;
    for (let zi = 0; zi < this._zones.length; zi++) {
      const zone = this._zones[zi];
      const halfW = zone.width * 0.46;
      const x  = zone.x - halfW;
      const bw = zone.width * 0.92;
      if (this._depth3d) {
        _drawSlab(ctx, x, slabTop, bw, slabH, zone.color);
      } else {
        ctx.fillStyle = hexAlpha(zone.color, 0.07);
        _roundRect(ctx, x, slabTop, bw, slabH, 8);
        ctx.fill();
        ctx.strokeStyle = hexAlpha(zone.color, 0.16);
        ctx.lineWidth = 1;
        _roundRect(ctx, x, slabTop, bw, slabH, 8);
        ctx.stroke();
      }
    }

    // ── Edges (signed weights: blue = +, orange = −, thickness = |w|) ──────
    const flow = 0.4 + 0.6 * this._trainLoss;
    for (const e of this._edges) {
      const mag = Math.abs(e.weight);
      const alpha = (0.10 + mag * 0.5) * flow;
      ctx.beginPath();
      ctx.moveTo(e.a.x, e.a.y);
      ctx.lineTo(e.b.x, e.b.y);
      ctx.strokeStyle = hexAlpha(e.weight >= 0 ? EDGE_POS : EDGE_NEG, alpha);
      ctx.lineWidth = 0.4 + mag * 2.4;
      ctx.stroke();
    }

    // ── Attention beams (all-to-all shimmer inside attention zones) ────────
    for (const zone of this._zones) {
      if (zone.visualType !== 'attention') continue;
      this._drawAttentionBeams(ctx, zone);
    }

    // ── Gradient stream (backward particles, output → input) ──────────────
    if (this._showGrad) {
      for (const p of this._gradParticles) {
        const idx  = Math.floor(p.t);
        const frac = p.t - idx;
        if (idx >= p.path.length - 1) continue;
        const a = p.path[idx];
        const b = p.path[idx + 1];
        const x = a.x + (b.x - a.x) * frac;
        const y = a.y + (b.y - a.y) * frac;
        ctx.beginPath();
        ctx.arc(x, y, 1.8, 0, Math.PI * 2);
        ctx.fillStyle = hexAlpha(GRAD_COLOR, 0.6);
        ctx.fill();
        // small trailing tick to suggest direction
        ctx.beginPath();
        ctx.moveTo(x, y);
        ctx.lineTo(x + (b.x - a.x) * 0.04, y + (b.y - a.y) * 0.04);
        ctx.strokeStyle = hexAlpha(GRAD_COLOR, 0.3);
        ctx.lineWidth = 1;
        ctx.stroke();
      }
    }

    // ── Forward particles ─────────────────────────────────────────────────
    for (const p of this._particles) {
      const idx  = Math.floor(p.t);
      const frac = p.t - idx;
      if (idx >= p.path.length - 1) continue;
      const a   = p.path[idx];
      const b   = p.path[idx + 1];
      const x   = a.x + (b.x - a.x) * frac;
      const y   = a.y + (b.y - a.y) * frac;
      const col = this._zones[idx]?.color ?? ZONE_COLORS.generic;

      ctx.beginPath();
      ctx.arc(x, y, 2.5, 0, Math.PI * 2);
      ctx.fillStyle = hexAlpha(col, p.alpha);
      ctx.fill();

      // Glow
      const grd = ctx.createRadialGradient(x, y, 0, x, y, 6);
      grd.addColorStop(0, hexAlpha(col, p.alpha * 0.45));
      grd.addColorStop(1, 'transparent');
      ctx.beginPath();
      ctx.arc(x, y, 6, 0, Math.PI * 2);
      ctx.fillStyle = grd;
      ctx.fill();
    }

    // ── Recurrent self-loop motifs (LSTM/GRU/RNN) ─────────────────────────
    for (const zone of this._zones) {
      if (zone.visualType !== 'recurrent') continue;
      this._drawRecurrentLoops(ctx, zone);
    }

    // ── Nodes ─────────────────────────────────────────────────────────────
    for (let zi = 0; zi < this._zones.length; zi++) {
      const zone = this._zones[zi];
      const col  = zone.color;
      for (const node of zone.nodes) {
        const hovered = node === this._hoverNode;
        const r     = (5 + node.activation * 5) * (hovered ? 1.6 : 1);
        const alpha = node.dead ? 0.08 : 0.3 + node.activation * 0.7;

        // Outer glow
        const grd = ctx.createRadialGradient(node.x, node.y, 0, node.x, node.y, r * 2.8);
        grd.addColorStop(0, hexAlpha(node.dead ? '#6b7280' : col, alpha * 0.5));
        grd.addColorStop(1, 'transparent');
        ctx.beginPath();
        ctx.arc(node.x, node.y, r * 2.8, 0, Math.PI * 2);
        ctx.fillStyle = grd;
        ctx.fill();

        // Core
        ctx.beginPath();
        ctx.arc(node.x, node.y, r, 0, Math.PI * 2);
        ctx.fillStyle = hexAlpha(node.dead ? '#6b7280' : col, alpha);
        ctx.fill();

        // Bright centre
        ctx.beginPath();
        ctx.arc(node.x, node.y, r * 0.35, 0, Math.PI * 2);
        ctx.fillStyle = hexAlpha('#ffffff', alpha * 0.7);
        ctx.fill();

        // Hover ring
        if (hovered) {
          ctx.beginPath();
          ctx.arc(node.x, node.y, r + 3, 0, Math.PI * 2);
          ctx.strokeStyle = hexAlpha('#ffffff', 0.85);
          ctx.lineWidth = 1.5;
          ctx.stroke();
        }
      }
    }

    // ── Accuracy progress ring on output zone ─────────────────────────────
    const outZone = this._zones.at(-1);
    if (outZone) {
      const cx     = outZone.x;
      const cy     = h * 0.5;
      const ringR  = Math.min(outZone.width * 0.42, 22);
      const arc    = this._valAcc * Math.PI * 2;
      const pulse  = 0.6 + 0.4 * Math.sin(this._t * 2);

      // Background ring
      ctx.beginPath();
      ctx.arc(cx, cy, ringR, 0, Math.PI * 2);
      ctx.strokeStyle = hexAlpha(outZone.color, 0.12);
      ctx.lineWidth = 3;
      ctx.stroke();

      // Progress arc
      ctx.beginPath();
      ctx.arc(cx, cy, ringR, -Math.PI / 2, -Math.PI / 2 + arc);
      ctx.strokeStyle = hexAlpha(outZone.color, 0.7 * pulse);
      ctx.lineWidth = 3;
      ctx.stroke();

      // Overfitting warning: pulsing red halo around output zone
      if (this._overfit) {
        const overPulse = 0.4 + 0.6 * Math.abs(Math.sin(this._t * 3));
        ctx.beginPath();
        ctx.arc(cx, cy, ringR + 6, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(239,68,68,${overPulse * 0.55})`;
        ctx.lineWidth = 2.5;
        ctx.stroke();
      }
    }

    // ── Per-layer gradient-magnitude bars (above the bottom labels) ───────
    // Only when we have REAL captured gradients — never an invented curve.
    if (this._showGrad && this._hasRealGrad) {
      const barMax = 14;
      const by = h - 34;
      for (const zone of this._zones) {
        if (!(zone.gradMag > 0)) continue;  // skip layers with no captured grad
        const bh = Math.max(1, zone.gradMag * barMax);
        const bx = zone.x - 8;
        // track
        ctx.fillStyle = hexAlpha(GRAD_COLOR, 0.12);
        ctx.fillRect(bx, by - barMax, 4, barMax);
        // fill
        ctx.fillStyle = hexAlpha(GRAD_COLOR, 0.75);
        ctx.fillRect(bx, by - bh, 4, bh);
        // ∇ glyph
        ctx.font = '8px DM Sans, sans-serif';
        ctx.textAlign = 'left';
        ctx.fillStyle = hexAlpha(GRAD_COLOR, 0.65);
        ctx.fillText('∇', bx + 6, by - 1);
      }
    }

    // ── Zone labels (technical + plain English, both at the bottom) ────────
    // Both labels are always shown but truncated per-zone so adjacent labels
    // don't bleed into each other. Plain labels get an alias map first
    // (shortens "Pattern finder" → "Patterns" etc. when room is tight)
    // then the binary-search ellipsis fitter takes whatever's left.
    ctx.textAlign = 'center';
    for (const zone of this._zones) {
      const budget = Math.max(20, zone.width * 0.95);  // px of horizontal room

      // Technical label (bold) — truncated if needed.
      ctx.font      = 'bold 10px DM Sans, sans-serif';
      ctx.fillStyle = hexAlpha(zone.color, 0.95);
      ctx.fillText(_fitText(ctx, zone.techLabel, budget), zone.x, h - 20);

      // Plain-English label — pick a shorter alias when the zone is narrow
      // so we don't waste the available pixels on a leading "Pat…" stub.
      ctx.font      = '8.5px DM Sans, sans-serif';
      ctx.fillStyle = hexAlpha(zone.color, 0.55);
      const plain = _shortenPlainLabel(zone.plainLabel, budget, ctx);
      ctx.fillText(plain, zone.x, h - 8);
    }

    // ── Flash labels (zone-crossing micro-captions) ───────────────────────
    ctx.font      = '8px DM Sans, sans-serif';
    ctx.textAlign = 'center';
    for (const fl of this._flashes) {
      ctx.fillStyle = `rgba(255,255,255,${fl.alpha * 0.9})`;
      ctx.fillText(fl.label, fl.x, fl.y);
    }

    // (Architecture summary is rendered as an HTML chip by HeroPanel — keeping
    //  it off-canvas avoids overlapping the OUTPUT zone label.)
  }

  /**
   * Self-attention beam web: shimmering all-to-all connections among a zone's
   * own nodes. Intensity breathes with time to convey "reading full context".
   */
  _drawAttentionBeams(ctx, zone) {
    const nodes = zone.nodes;
    const base  = 0.20 + 0.10 * Math.sin(this._t * 1.6);
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j];
        // each pair shimmers on its own phase
        const sh = 0.5 + 0.5 * Math.sin(this._t * 2.2 + (i * 3 + j));
        const alpha = base * (0.45 + 0.55 * sh) * (0.5 + 0.5 * this._valAcc);
        ctx.beginPath();
        // curve the beam slightly outward for a lens-like look
        const mx = zone.x + (i % 2 === 0 ? -1 : 1) * zone.width * 0.20;
        const my = (a.y + b.y) / 2;
        ctx.moveTo(a.x, a.y);
        ctx.quadraticCurveTo(mx, my, b.x, b.y);
        ctx.strokeStyle = hexAlpha(zone.color, alpha);
        ctx.lineWidth = 1.1;
        ctx.stroke();
      }
    }
  }

  /**
   * Recurrent memory loops: each node sprouts a small feedback arc on its left
   * with a pulse orbiting it — the hidden state feeding back into itself.
   */
  _drawRecurrentLoops(ctx, zone) {
    const loopR = 9;
    for (const node of zone.nodes) {
      const cx = node.x - 14;
      const cy = node.y;
      // feedback arc (almost full circle for a clear "loop" read)
      ctx.beginPath();
      ctx.arc(cx, cy, loopR, -Math.PI * 0.75, Math.PI * 0.75, false);
      ctx.strokeStyle = hexAlpha(zone.color, 0.7);
      ctx.lineWidth = 1.8;
      ctx.stroke();
      // arrow head suggesting the return into the node
      const ax = node.x - 5, ay = node.y - 5;
      ctx.beginPath();
      ctx.moveTo(ax, ay);
      ctx.lineTo(ax - 4, ay - 2);
      ctx.lineTo(ax - 2, ay + 3.5);
      ctx.closePath();
      ctx.fillStyle = hexAlpha(zone.color, 0.75);
      ctx.fill();
      // orbiting pulse on the loop
      const ang = -Math.PI * 0.75 + ((this._t * 2 + node.phase) % (Math.PI * 1.5));
      const px = cx + Math.cos(ang) * loopR;
      const py = cy + Math.sin(ang) * loopR;
      ctx.beginPath();
      ctx.arc(px, py, 2.2, 0, Math.PI * 2);
      ctx.fillStyle = hexAlpha(zone.color, 0.95);
      ctx.fill();
    }
  }
}

// ── helpers ───────────────────────────────────────────────────────────────────

/** Number of visible nodes for a zone. */
function _zoneNodeCount(zone) {
  if (zone.visualType === 'input'  || zone.visualType === 'output') return 4;
  if (zone.visualType === 'norm')  return 3;
  if (!zone.params)                return 6;
  if (zone.params > 5_000_000)     return 8;
  if (zone.params > 100_000)       return 6;
  return 4;
}

/**
 * Draw a zone as a pseudo-3D isometric slab: a front face plus a top and a
 * right face offset by (DEPTH_DX, -DEPTH_DY). Pure Canvas 2D — no WebGL.
 * Faces use distinct brightness (top brightest, side darkest) + bright top
 * edges so the extrusion reads as a solid 3D block.
 * @param {CanvasRenderingContext2D} ctx
 */
function _drawSlab(ctx, x, y, w, h, color) {
  const dx = DEPTH_DX, dy = DEPTH_DY;

  // Right face (drawn first, behind) — darkest, vertical gradient for shading.
  const rg = ctx.createLinearGradient(x + w, y, x + w + dx, y + h);
  rg.addColorStop(0, hexAlpha(color, 0.20));
  rg.addColorStop(1, hexAlpha(color, 0.06));
  ctx.beginPath();
  ctx.moveTo(x + w, y);
  ctx.lineTo(x + w + dx, y - dy);
  ctx.lineTo(x + w + dx, y + h - dy);
  ctx.lineTo(x + w, y + h);
  ctx.closePath();
  ctx.fillStyle = rg;
  ctx.fill();

  // Top face (parallelogram) — brightest.
  const tg = ctx.createLinearGradient(x, y - dy, x, y);
  tg.addColorStop(0, hexAlpha(color, 0.40));
  tg.addColorStop(1, hexAlpha(color, 0.22));
  ctx.beginPath();
  ctx.moveTo(x, y);
  ctx.lineTo(x + dx, y - dy);
  ctx.lineTo(x + w + dx, y - dy);
  ctx.lineTo(x + w, y);
  ctx.closePath();
  ctx.fillStyle = tg;
  ctx.fill();

  // Front face — subtle vertical gradient.
  const fg = ctx.createLinearGradient(x, y, x, y + h);
  fg.addColorStop(0, hexAlpha(color, 0.12));
  fg.addColorStop(1, hexAlpha(color, 0.04));
  ctx.fillStyle = fg;
  ctx.fillRect(x, y, w, h);

  // Edges: bright top + front-left for crisp definition.
  ctx.strokeStyle = hexAlpha(color, 0.55);
  ctx.lineWidth = 1.2;
  ctx.beginPath();
  ctx.moveTo(x, y);
  ctx.lineTo(x + dx, y - dy);
  ctx.lineTo(x + w + dx, y - dy);
  ctx.stroke();

  ctx.strokeStyle = hexAlpha(color, 0.22);
  ctx.lineWidth = 1;
  ctx.strokeRect(x, y, w, h);
}

/** Canvas rounded-rect path helper (no fill/stroke). */
function _roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

/** Compact parameter-count label, e.g. 23.5M / 2.1K. */
function _fmtParams(n) {
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
  return String(n);
}

function _escTip(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/**
 * Pick the most informative plain-English label that fits the zone's
 * pixel budget. Tries the original first, then a single-word shorthand,
 * then the leading word, then finally a truncated-with-ellipsis fallback.
 * Returns whichever VARIANT is the longest that still fits — so a wider
 * zone keeps the friendly phrase, and a narrow zone keeps a meaningful
 * word instead of a useless "Pat…" stub.
 */
function _shortenPlainLabel(label, budgetPx, ctx) {
  if (!label) return '';
  const candidates = [label];
  // Compact phrase → single representative word for common plain labels.
  const aliases = {
    'Pattern finder':   'Patterns',
    'Feature block':    'Features',
    'Feature extractor':'Features',
    'Pyramid pooling':  'Pooling',
    'Upsampling':       'Upsamp',
    'Symbol mapper':    'Embedding',
    'Remembers context':'Memory',
    'Reads full context':'Attention',
    'Raw data':         'Input',
    'Decision':         'Output',
    'Stabilises':       'Norm',
  };
  if (aliases[label]) candidates.push(aliases[label]);
  // Leading word fallback (often still meaningful: "Pattern", "Feature")
  const firstWord = label.split(/\s+/, 1)[0];
  if (firstWord && firstWord !== label) candidates.push(firstWord);
  for (const c of candidates) {
    if (ctx.measureText(c).width <= budgetPx) return c;
  }
  // None fits as-is — fall back to ellipsis-trim of the original phrase.
  return _fitText(ctx, label, budgetPx);
}

/**
 * Trim *text* with an ellipsis until it fits the given pixel budget at the
 * context's current font. Used so per-zone bottom labels never bleed into
 * neighbouring zones when many layers share a narrow panel.
 */
function _fitText(ctx, text, budgetPx) {
  if (!text) return '';
  if (ctx.measureText(text).width <= budgetPx) return text;
  let lo = 0, hi = text.length;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    const candidate = text.slice(0, mid) + '…';
    if (ctx.measureText(candidate).width <= budgetPx) lo = mid;
    else hi = mid - 1;
  }
  return lo === 0 ? '…' : text.slice(0, lo) + '…';
}
