"""`epochix doctor` must tell the truth about the accelerator it is on.

Activation capture uses PyTorch/Keras forward hooks — framework API, not a
vendor one — and there is no device gating anywhere in the SDK. So it should
work on Apple MPS and AMD ROCm exactly as on CUDA. "Should" is not "does":
nobody has run it there, and an untested path is not a supported one.

Rather than claim either way, doctor runs the real capturer on the device that
is actually present and reports what came back. On a backend we have not
verified it also asks for that line, because a tester's paste is the only thing
that turns "should work" into "known to work".
"""

from __future__ import annotations

import sys

import pytest

from epochix.cli import _accelerator_report

torch = pytest.importorskip("torch")


def _text() -> str:
    return "\n".join(_accelerator_report())


class TestWithoutTorch:
    def test_it_says_so_instead_of_crashing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # A module set to None makes `import torch` raise ImportError.
        monkeypatch.setitem(sys.modules, "torch", None)
        out = _text()
        assert "PyTorch not installed" in out
        # doctor is what you run WHEN SOMETHING IS WRONG; it must never be the
        # thing that breaks.
        assert "Traceback" not in out


class TestOnCpu:
    def _force_cpu(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
        monkeypatch.setattr(torch.cuda, "device_count", lambda: 0)
        monkeypatch.setattr(torch.backends.mps, "is_available", lambda: False)
        if hasattr(torch, "xpu"):
            monkeypatch.setattr(torch.xpu, "is_available", lambda: False)

    def test_capture_works_with_no_gpu_at_all(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The claim under test: capture is not NVIDIA-only.

        With every accelerator hidden, the hooks still return real per-layer
        magnitudes — so nothing in this path needs CUDA.
        """
        self._force_cpu(monkeypatch)
        out = _text()
        assert "accelerator    cpu" in out
        assert "activations    working" in out

    def test_a_verified_backend_is_not_asked_about(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._force_cpu(monkeypatch)
        assert "please report" not in _text()


class TestOnAnUnverifiedBackend:
    """Apple MPS, as it would look on a Mac we do not have."""

    def _force_mps(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
        monkeypatch.setattr(torch.cuda, "device_count", lambda: 0)
        monkeypatch.setattr(torch.backends.mps, "is_available", lambda: True)

    def test_it_is_named_not_hidden(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._force_mps(monkeypatch)
        assert "accelerator    mps" in _text()

    def test_the_result_is_requested(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._force_mps(monkeypatch)
        out = _text()
        assert "not verified by us" in out
        assert "please report" in out

    def test_it_is_requested_even_when_capture_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """On this machine `.to("mps")` raises, which is the failure case.

        Gating the invitation on success hid it in exactly the situation worth
        hearing about: capture breaking on a backend nobody has tried.
        """
        self._force_mps(monkeypatch)
        out = _text()
        assert "ERROR" in out or "working" in out
        assert "please report" in out

    def test_a_failure_never_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._force_mps(monkeypatch)
        assert _accelerator_report()  # returned lines rather than propagating
