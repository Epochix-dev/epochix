# Design scope — real activation magnitudes in the Network State panel

Status: **proposed** · Target: a minor release (0.5.0) · Owner: TBD

## Problem

The Network State panel now draws the **real architecture** (0.4.0), but the
node "activity" and edge flow animating inside it are decorative — `activation
= Math.random()` (`BrainCanvas.js:364,424`). It's labelled *"schematic —
illustrative, not measured weights"*, which is honest, but the goal is for the
animation to reflect **real per-layer activation magnitudes** captured from the
model during training, so nothing on the panel is invented.

## Goal

Per layer already shown in the architecture, stream a **real scalar** that
summarises that layer's output activations for the current step — mean |activation|
(and optionally the fraction of dead/zero units) — and drive the node brightness
/ size from it instead of a random number.

## Non-goals

- Per-neuron values (we show a fixed number of illustrative nodes per zone; the
  *zone-level* magnitude is what becomes real).
- Real per-edge weights (weights aren't forward-pass observable cheaply; edges
  stay schematic, and the legend keeps saying so).
- Gradient magnitudes (possible follow-up via backward hooks; out of scope here).
- Frameworks other than PyTorch in v1 (Keras/TF hooks are a later add).

## Approach

### 1. Capture — forward hooks (PyTorch), opt-in, sampled

`LiveReporter(model=…, capture_activations=True)` registers
`module.register_forward_hook` on exactly the parameter-bearing modules already
selected by `architecture_from_model` (same list, same names — so activations
line up 1:1 with the drawn layers).

Each hook computes a **cheap scalar** from the output tensor and stores it in a
thread-safe dict keyed by layer name:

```python
def _hook(name):
    def fn(_module, _inp, out):
        t = out[0] if isinstance(out, (tuple, list)) else out
        if not torch.is_tensor(t):
            return
        # detached, no grad; .item() forces a GPU→CPU sync, so THROTTLE (below)
        buf[name] = {
            "mag":  t.detach().abs().mean().item(),
            "dead": (t.detach() == 0).float().mean().item(),  # ReLU sparsity
        }
    return fn
```

Critical performance guards (these are the whole ballgame):

- **Throttle by wall-clock, not by step.** A hook that calls `.item()` every
  forward pass forces a GPU sync and can slow training 5–30%. Capture at most
  ~2 Hz: keep a `last_capture` timestamp; the hook early-returns unless
  `time.monotonic() - last_capture > 0.5`. Training-speed impact then rounds to
  zero.
- **No autograd retention:** `.detach()`, never keep the tensor.
- **Fail-open:** any exception in a hook is swallowed (never break training) and
  disables that hook.
- **Cap layers:** reuse the `_MAX_LAYERS` (24) cap so wide models don't spam.
- **train vs eval:** capture during `model.training == True` only, so we report
  the trainee's activations, not a possibly-different eval path.

### 2. Transport — a new `activations` WS message + light persistence

- Add `"activations"` to `WSMessage.type` (`models.py:97`) and to
  `Hub.make_message`'s `Literal` (`hub.py:119`).
- The `LiveReporter` flushes the current `buf` **once per `log()` call**
  (i.e. per epoch — same cadence as metrics, not per forward pass) as:
  ```json
  { "type": "activations", "run_id": …, "seq": …,
    "payload": { "layers": { "face.0": {"mag":0.42,"dead":0.13}, … } } }
  ```
  Values are normalised client-side per-run to [0,1] (divide by the running max
  per layer) so brightness is comparable across layers of different scales.
- Persist the **latest** snapshot in `run.config["activations"]` via
  `update_run_config` so a dashboard opened mid/after-run still shows real
  values (not just live WS subscribers). One row, overwritten — no history bloat.

### 3. Consume — frontend

- `ws-client.js`: add a `case 'activations'` that stores
  `state.activations` (layer-name → {mag, dead}); `store.js` gains the field.
- `BrainCanvas.js`:
  - When `state.activations` is present, node `activation` for a zone = the real
    normalised `mag` for that layer (`activation = Math.random()` at line 364 /
    the sin update at 424 becomes: seed from real value, animate gently around
    it so it still *moves* without inventing the level).
  - `node.dead` uses the real `dead` fraction instead of `Math.random() < 0.001`.
  - When absent → keep today's schematic animation **but** relabel the legend
    from "schematic" to "no live activations" so the distinction is explicit.
- The legend text becomes conditional: **"live activations"** (real) vs
  **"schematic — enable capture_activations"** (fallback). Never claim "live"
  when it's random.

## API

```python
LiveReporter(
    task="gaze", primary_metric="val_mae_cm", model=model,
    capture_activations=True,      # NEW — default False (zero overhead unless asked)
    activation_hz=2.0,             # NEW — capture rate cap
)
```

Default **off**: no behaviour change, no overhead for users who don't opt in.
When on, the hooks self-remove on `finish()`.

## Edge cases / risks

| Case | Handling |
|---|---|
| Layer output is a tuple/dict (attention, LSTM) | take element 0 if tensor, else skip that layer (stays schematic) |
| Non-tensor / control-flow modules | hook fail-open → skipped |
| DataParallel / DDP | capture on rank 0 only; hooks on the underlying module |
| `.item()` sync cost | wall-clock throttle (≤ activation_hz); measured overhead target < 2% |
| Model moved to GPU after reporter start | hooks attach to modules, survive `.to(device)` |
| Very deep model | `_MAX_LAYERS` cap already bounds it |
| torch not installed | `capture_activations` silently no-ops (SDK already torch-optional) |

## Test plan

- Unit: a fake module whose forward returns a known tensor → hook records the
  expected mean-abs and dead-fraction; tuple output → skipped; exception in
  forward → hook disabled, training continues.
- Throttle: N forward passes in < window → exactly 1 capture.
- Integration: `LiveReporter(model=…, capture_activations=True)` on a tiny real
  torch model → `run.config["activations"]` populated with the real layer names,
  values in range, and an `activations` WS message observed on the hub.
- Frontend (vitest): `ws-client` routes `activations` into store; BrainCanvas
  uses real `mag` when present and falls back cleanly when absent.
- Perf smoke: 200 forward passes with capture on vs off → wall-clock delta
  under the target threshold.

## Effort

~1 focused implementation pass: SDK hooks + throttle (~120 LoC + tests),
transport wiring (~30 LoC, mirrors the existing `architecture` message),
frontend consumption + conditional legend (~60 LoC + a vitest). Medium risk,
concentrated in the perf-throttling correctness.

## Rollout

Ships behind the opt-in flag as **0.5.0**. Docs: one SDK example. The legend
wording change makes the real-vs-schematic distinction visible either way, which
keeps the honesty guarantee whether or not a user enables capture.
