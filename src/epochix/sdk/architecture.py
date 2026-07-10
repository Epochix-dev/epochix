"""Extract a *real* architecture description from a live model object.

Used by :class:`~epochix.sdk.live_reporter.LiveReporter` so the dashboard's
Network State panel shows the actual model the user is training — real layer
names, real types, real parameter counts — instead of a placeholder. If a
model can't be introspected, this returns ``None`` and the dashboard shows an
honest "no architecture" state rather than inventing one.

Supported: PyTorch ``nn.Module`` and Keras/TF ``Model`` (duck-typed, so neither
framework is a hard dependency).
"""

from __future__ import annotations

from epochix.parsers.architecture_parser import _MAX_LAYERS, ArchLayer, _classify


def _fmt_params(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _layer(idx: int, name: str, layer_type: str, params: int) -> dict[str, object]:
    return ArchLayer(
        idx=idx,
        name=name,
        layer_type=layer_type,
        params=params,
        params_str=_fmt_params(params),
        **_classify(layer_type),
    ).to_dict()


def torch_param_modules(model: object) -> list[tuple[str, object]]:
    """The parameter-bearing sub-modules that make up the drawn architecture.

    Returns ``(name, module)`` pairs in definition order — a module that owns
    parameters *directly* (Conv2d, Linear, LayerNorm, MultiheadAttention, …).
    Pure containers (Sequential) own none — their children are captured instead
    — and activations/dropout own none. The name matches what
    :func:`architecture_from_model` labels the layer, so activation hooks
    registered on these modules line up 1:1 with the drawn layers. Capped at
    ``_MAX_LAYERS`` and never raises (introspection must not crash training).
    """
    named_modules = getattr(model, "named_modules", None)
    if named_modules is None:
        return []
    out: list[tuple[str, object]] = []
    for name, mod in named_modules():
        if mod is model:
            continue  # skip the root container
        try:
            direct = sum(p.numel() for p in mod.parameters(recurse=False))
        except Exception:  # noqa: BLE001 — never let introspection crash training
            continue
        if direct <= 0:
            continue
        out.append((name or type(mod).__name__, mod))
        if len(out) >= _MAX_LAYERS:
            break
    return out


def _from_torch(model: object) -> list[dict[str, object]] | None:
    """Every parameter-bearing sub-module, in definition order (real values)."""
    mods = torch_param_modules(model)
    if not mods:
        return None
    layers: list[dict[str, object]] = []
    for idx, (name, mod) in enumerate(mods):
        direct = sum(p.numel() for p in mod.parameters(recurse=False))  # type: ignore[attr-defined]
        layers.append(_layer(idx, name, type(mod).__name__, int(direct)))
    return layers or None


def _from_keras(model: object) -> list[dict[str, object]] | None:
    klayers = getattr(model, "layers", None)
    if not klayers:
        return None
    layers: list[dict[str, object]] = []
    for idx, layer in enumerate(klayers[:_MAX_LAYERS]):
        try:
            params = int(layer.count_params())
        except Exception:  # noqa: BLE001
            params = 0
        name = getattr(layer, "name", None) or type(layer).__name__
        layers.append(_layer(idx, name, type(layer).__name__, params))
    return layers or None


def architecture_from_model(model: object) -> list[dict[str, object]] | None:
    """Return a list of real layer dicts for *model*, or ``None`` if it can't
    be introspected. Never raises — introspection must not break training."""
    if model is None:
        return None
    try:
        # PyTorch: has named_modules(); Keras: has .layers.
        if hasattr(model, "named_modules"):
            return _from_torch(model)
        if hasattr(model, "layers"):
            return _from_keras(model)
    except Exception:  # noqa: BLE001
        return None
    return None
