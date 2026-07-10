"""SDK activation capture — real forward/backward hooks → real per-layer scalars.

These verify the performance-critical throttle, the fail-open contract, and that
captured names line up 1:1 with the drawn architecture layers.
"""

from __future__ import annotations

import time

import pytest

from epochix.sdk.activations import ActivationCapturer
from epochix.sdk.architecture import architecture_from_model, torch_param_modules


def test_captures_real_values_aligned_with_architecture() -> None:
    torch = pytest.importorskip("torch")
    nn = torch.nn
    model = nn.Sequential(nn.Linear(8, 16), nn.ReLU(), nn.Linear(16, 4))

    cap = ActivationCapturer(model, hz=1000.0)  # effectively no throttle
    model.train()
    out = model(torch.randn(5, 8))
    out.pow(2).mean().backward()

    snap = cap.snapshot()
    arch_names = {layer["name"] for layer in (architecture_from_model(model) or [])}
    # Same modules the architecture draws — activations line up 1:1.
    assert set(snap) == arch_names
    for stats in snap.values():
        assert stats["mag"] >= 0.0
        assert 0.0 <= stats["dead"] <= 1.0
        assert stats["grad"] >= 0.0  # backward hooks captured gradient magnitude
    cap.remove()


def test_wall_clock_throttle_limits_capture_rate() -> None:
    torch = pytest.importorskip("torch")
    nn = torch.nn
    model = nn.Sequential(nn.Linear(4, 4))
    cap = ActivationCapturer(model, hz=5.0, gradients=False)  # >=0.2s between samples
    model.train()

    name = torch_param_modules(model)[0][0]
    model(torch.zeros(1, 4))  # first pass captures (dead == 1.0 for all-zero input)
    first = cap.snapshot()[name]["mag"]

    # A burst within the throttle window must NOT overwrite with a new sample.
    for _ in range(100):
        model(torch.randn(1, 4))
    assert cap.snapshot()[name]["mag"] == first

    time.sleep(0.25)  # past the window → next pass captures a fresh value
    model(torch.randn(1, 4))
    assert cap.snapshot()[name]["mag"] != first
    cap.remove()


def test_eval_mode_is_not_captured() -> None:
    torch = pytest.importorskip("torch")
    nn = torch.nn
    model = nn.Linear(4, 4)
    cap = ActivationCapturer(model, hz=1000.0, gradients=False)
    model.eval()
    with torch.no_grad():
        model(torch.randn(2, 4))
    assert cap.snapshot() == {}  # eval-path forward reports nothing
    cap.remove()


def test_tuple_output_takes_first_tensor() -> None:
    torch = pytest.importorskip("torch")
    nn = torch.nn

    class TupleOut(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.lin = nn.Linear(4, 4)

        def forward(self, x: object) -> tuple[object, object]:
            y = self.lin(x)
            return y, None  # attention/LSTM-style tuple output

    model = TupleOut()
    cap = ActivationCapturer(model, hz=1000.0, gradients=False)
    model.train()
    model(torch.randn(2, 4))
    assert cap.snapshot()["lin"]["mag"] >= 0.0
    cap.remove()


def test_fail_open_never_raises_and_no_op_without_model() -> None:
    # Non-model object → inert capturer, empty snapshot, safe teardown.
    cap = ActivationCapturer(object(), hz=2.0)
    assert cap.snapshot() == {}
    cap.remove()

    cap2 = ActivationCapturer("not a model")
    assert cap2.snapshot() == {}


def test_keras_style_call_wrapping() -> None:
    """Duck-typed Keras layer with .weights and .call → wrapped and unwrapped."""
    np = pytest.importorskip("numpy")

    class _Layer:
        def __init__(self, name: str) -> None:
            self.name = name
            self.weights = [object()]

        def call(self, x: object) -> object:  # noqa: D401 - mimics keras Layer.call
            return x

    class _Tensor:
        def __init__(self, arr: object) -> None:
            self._arr = arr

        def numpy(self) -> object:
            return self._arr

    class _Model:
        def __init__(self) -> None:
            self.layers = [_Layer("dense_1")]

    model = _Model()
    cap = ActivationCapturer(model, hz=1000.0)
    # Wrapping replaced .call; invoking it records stats.
    model.layers[0].call(_Tensor(np.array([1.0, 0.0, 3.0], dtype=np.float32)))
    snap = cap.snapshot()
    assert snap["dense_1"]["mag"] == pytest.approx(4.0 / 3.0)
    assert snap["dense_1"]["dead"] == pytest.approx(1.0 / 3.0)
    cap.remove()
    # Restored on teardown: calling again no longer records (snapshot frozen).
    model.layers[0].call(_Tensor(np.array([9.0, 9.0], dtype=np.float32)))
    assert cap.snapshot()["dense_1"]["mag"] == pytest.approx(4.0 / 3.0)
