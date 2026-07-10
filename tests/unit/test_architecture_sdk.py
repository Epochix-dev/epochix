"""SDK architecture extraction — real model → real layer records."""

from __future__ import annotations

import pytest

from epochix.sdk.architecture import architecture_from_model


def test_none_when_no_model() -> None:
    assert architecture_from_model(None) is None
    assert architecture_from_model("not a model") is None
    assert architecture_from_model(42) is None


def test_real_torch_model() -> None:
    torch = pytest.importorskip("torch")
    nn = torch.nn
    model = nn.Sequential(nn.Linear(10, 20), nn.ReLU(), nn.Dropout(0.1), nn.Linear(20, 2))
    arch = architecture_from_model(model)
    assert arch is not None
    # Only parameter-bearing layers (the two Linears); ReLU/Dropout are skipped.
    types = [layer["layer_type"] for layer in arch]
    assert types == ["Linear", "Linear"]
    # Parameter counts are the REAL values — sum equals the model's total.
    total = sum(p.numel() for p in model.parameters())
    assert sum(layer["params"] for layer in arch) == total  # type: ignore[misc]
    # Classified for the visual layer.
    assert all(layer["visual_type"] == "dense" for layer in arch)


def test_real_keras_style_model() -> None:
    """Duck-typed Keras model (.layers with count_params) — no TF dependency."""

    class _Layer:
        def __init__(self, name: str, n: int) -> None:
            self.name = name
            self._n = n

        def count_params(self) -> int:
            return self._n

    class _Model:
        layers = [_Layer("dense_1", 128), _Layer("dense_2", 10)]

    arch = architecture_from_model(_Model())
    assert arch is not None
    assert [layer["params"] for layer in arch] == [128, 10]
