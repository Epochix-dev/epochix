"""Capture *real* per-layer activation (and gradient) magnitudes at training time.

The Network State panel draws the real architecture (0.4.0); this module makes
the node "activity" animating inside it real too — mean ``|activation|`` and the
dead/zero fraction per layer, captured live from the model via forward hooks
(plus mean ``|gradient|`` via backward hooks). Everything here is opt-in and
fail-open: a hook that raises is swallowed and disabled, never breaking a
training run, and the whole thing is a no-op if PyTorch/Keras isn't the model.

Performance is the whole ballgame. ``.item()`` forces a GPU→CPU sync, so every
hook is **wall-clock throttled** (``activation_hz``, ~2 Hz default): the sync
frequency is bounded regardless of how fast the training loop spins, which keeps
the overhead rounding to zero.

Supported: PyTorch ``nn.Module`` and Keras 3 ``Model`` (duck-typed — neither is
a hard dependency).
"""

from __future__ import annotations

import contextlib
import threading
import time
from collections.abc import Callable

from epochix.sdk.architecture import torch_param_modules


class ActivationCapturer:
    """Registers hooks on a model and accumulates the latest per-layer scalars.

    Use :meth:`snapshot` to read the current ``{layer_name: {"mag", "dead",
    "grad"}}`` map (a copy, safe to hand off to another thread) and
    :meth:`remove` to detach every hook. Construction attaches the hooks; if the
    model can't be hooked the capturer is simply inert (``snapshot`` stays
    empty), so callers never need to special-case framework detection.
    """

    def __init__(self, model: object, hz: float = 2.0, *, gradients: bool = True) -> None:
        self._buf: dict[str, dict[str, float]] = {}
        self._lock = threading.Lock()
        self._handles: list[object] = []
        self._last: dict[str, float] = {}
        self._interval = 1.0 / max(float(hz), 0.1)
        self._gradients = gradients
        try:
            self._register(model)
        except Exception:  # noqa: BLE001 — capture is best-effort, never fatal
            self.remove()

    # -- registration ------------------------------------------------------
    def _register(self, model: object) -> None:
        if self._register_torch(model):
            return
        self._register_keras(model)

    def _register_torch(self, model: object) -> bool:
        mods = torch_param_modules(model)
        if not mods:
            return False
        for name, mod in mods:
            reg = getattr(mod, "register_forward_hook", None)
            if reg is None:
                return False  # not a torch module after all
            self._handles.append(reg(self._forward_hook(name)))
            if self._gradients:
                back = getattr(mod, "register_full_backward_hook", None)
                if back is not None:
                    self._handles.append(back(self._backward_hook(name)))
        if self._gradients and self._handles:
            # The input-side layer's inputs (the data batch) don't require grad,
            # so PyTorch warns once per backward that the full backward hook is
            # firing anyway. That's expected for our use — silence just that
            # message so opting into gradient capture doesn't spam the console.
            import warnings

            warnings.filterwarnings("ignore", message=".*Full backward hook is firing.*")
        return True

    def _register_keras(self, model: object) -> None:
        # Keras has no forward-hook mechanism; we wrap each parameter-bearing
        # layer's ``call`` so the output tensor flows through our scalar reducer.
        # Same fail-open contract: any error leaves the layer un-wrapped.
        layers = getattr(model, "layers", None)
        if layers is None:
            return
        for layer in layers:
            try:
                if not getattr(layer, "weights", None):
                    continue
                name = getattr(layer, "name", None) or type(layer).__name__
                self._wrap_keras_call(layer, name)
            except Exception:  # noqa: BLE001
                continue

    def _wrap_keras_call(self, layer: object, name: str) -> None:
        orig = layer.call  # type: ignore[attr-defined]

        def wrapped(*args: object, **kwargs: object) -> object:
            out = orig(*args, **kwargs)
            with contextlib.suppress(Exception):
                self._record_keras(name, out)
            return out

        layer.call = wrapped  # type: ignore[attr-defined]
        self._handles.append(_KerasUnwrap(layer, orig))

    # -- hooks -------------------------------------------------------------
    def _throttled(self, name: str) -> bool:
        now = time.monotonic()
        if now - self._last.get(name, 0.0) < self._interval:
            return True
        self._last[name] = now
        return False

    def _forward_hook(self, name: str) -> Callable[..., None]:
        def hook(module: object, _inp: object, output: object) -> None:
            try:
                # Report the trainee's activations, not a (possibly different)
                # eval-path forward. ``training`` defaults True if unset.
                if getattr(module, "training", True) is False:
                    return
                if self._throttled(name):
                    return
                stats = _tensor_stats(output)
                if stats is None:
                    return
                mag, dead = stats
                with self._lock:
                    slot = self._buf.setdefault(name, {})
                    slot["mag"] = mag
                    slot["dead"] = dead
            except Exception:  # noqa: BLE001 — never break the forward pass
                return

        return hook

    def _backward_hook(self, name: str) -> Callable[..., None]:
        def hook(_module: object, grad_input: object, grad_output: object) -> None:
            try:
                if self._throttled(name + "\x00grad"):
                    return
                mag = _grad_mag(grad_output)
                if mag is None:
                    return
                with self._lock:
                    self._buf.setdefault(name, {})["grad"] = mag
            except Exception:  # noqa: BLE001
                return

        return hook

    def _record_keras(self, name: str, output: object) -> None:
        if self._throttled(name):
            return
        stats = _tensor_stats(output)
        if stats is None:
            return
        mag, dead = stats
        with self._lock:
            slot = self._buf.setdefault(name, {})
            slot["mag"] = mag
            slot["dead"] = dead

    # -- readout / teardown ------------------------------------------------
    def snapshot(self) -> dict[str, dict[str, float]]:
        with self._lock:
            return {k: dict(v) for k, v in self._buf.items()}

    def remove(self) -> None:
        for h in self._handles:
            with contextlib.suppress(Exception):
                h.remove()  # type: ignore[attr-defined]
        self._handles.clear()


class _KerasUnwrap:
    """Handle that restores a Keras layer's original ``call`` on ``remove``."""

    def __init__(self, layer: object, orig: Callable[..., object]) -> None:
        self._layer = layer
        self._orig = orig

    def remove(self) -> None:
        self._layer.call = self._orig  # type: ignore[attr-defined]


def _tensor_stats(output: object) -> tuple[float, float] | None:
    """``(mean_abs, dead_fraction)`` for a tensor-ish output, or ``None`` to skip.

    Tuple/list outputs (attention, LSTM) contribute their first tensor element;
    anything non-floating-point or non-tensor is skipped so that layer simply
    stays schematic instead of reporting a bogus number.
    """
    t = output[0] if isinstance(output, (tuple, list)) and output else output
    try:
        import torch
    except Exception:  # noqa: BLE001
        torch = None  # type: ignore[assignment]
    if torch is not None and torch.is_tensor(t):
        t = t.detach()
        if not t.is_floating_point():
            return None
        if t.numel() == 0:
            return None
        mag = float(t.abs().mean().item())
        dead = float((t == 0).float().mean().item())
        return mag, dead
    # Keras/TF eager tensor: has ``.numpy()`` and a float dtype. Reduce cheaply.
    numpy_fn = getattr(t, "numpy", None)
    if numpy_fn is None:
        return None
    try:
        import numpy as np

        arr = np.asarray(numpy_fn())
        if arr.size == 0 or not np.issubdtype(arr.dtype, np.floating):
            return None
        mag = float(np.abs(arr).mean())
        dead = float((arr == 0).mean())
        return mag, dead
    except Exception:  # noqa: BLE001
        return None


def _grad_mag(grad_output: object) -> float | None:
    """Mean ``|grad|`` over the first gradient tensor, or ``None`` to skip."""
    g = grad_output[0] if isinstance(grad_output, (tuple, list)) and grad_output else grad_output
    try:
        import torch
    except Exception:  # noqa: BLE001
        return None
    if g is None or not torch.is_tensor(g) or not g.is_floating_point() or g.numel() == 0:
        return None
    return float(g.detach().abs().mean().item())
