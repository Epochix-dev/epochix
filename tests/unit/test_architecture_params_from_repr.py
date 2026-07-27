"""Parameter counts derived from a plain ``print(model)`` dump.

`print(model)` prints no parameter counts, and the module-repr parser used to
hardcode 0 — so the architecture panel reported "0 params" for every layer of a
model with ~207K of them. A module's repr does carry the shapes its parameters
are built from, so for the weight-bearing built-ins the count is derivable
exactly.

Every expected value below was produced by real PyTorch (2.11):
``sum(p.numel() for p in child.parameters())`` on the module whose repr is the
input. They are not hand-computed.
"""

from __future__ import annotations

from epochix.parsers.architecture_parser import parse_architecture

# nn.Sequential(Conv2d(1,32,3,padding=1), ReLU, MaxPool2d(2),
#               Conv2d(32,32,3,padding=1), ReLU, MaxPool2d(2), Flatten,
#               Linear(1568,128), ReLU, Dropout(0.25), Linear(128,10))
COLD_START_CNN = """Sequential(
  (0): Conv2d(1, 32, kernel_size=(3, 3), stride=(1, 1), padding=(1, 1))
  (1): ReLU()
  (2): MaxPool2d(kernel_size=2, stride=2, padding=0, dilation=1, ceil_mode=False)
  (3): Conv2d(32, 32, kernel_size=(3, 3), stride=(1, 1), padding=(1, 1))
  (4): ReLU()
  (5): MaxPool2d(kernel_size=2, stride=2, padding=0, dilation=1, ceil_mode=False)
  (6): Flatten(start_dim=1, end_dim=-1)
  (7): Linear(in_features=1568, out_features=128, bias=True)
  (8): ReLU()
  (9): Dropout(p=0.25, inplace=False)
  (10): Linear(in_features=128, out_features=10, bias=True)
)"""


def test_the_reported_model_is_not_all_zeros() -> None:
    """The exact shape from the cold-start report: ~207K params shown as 0."""
    layers = parse_architecture(COLD_START_CNN.splitlines())
    assert layers, "no layers parsed"
    assert sum(layer.params for layer in layers) == 211690
    assert any(layer.params > 0 for layer in layers), "every layer reported 0 params"


def test_each_layer_matches_torch_numel() -> None:
    """Per layer, in order. ReLU/Flatten are dropped as visual noise upstream."""
    layers = parse_architecture(COLD_START_CNN.splitlines())
    assert [layer.layer_type for layer in layers] == [
        "Conv2d",
        "MaxPool2d",
        "Conv2d",
        "MaxPool2d",
        "Linear",
        "Dropout",
        "Linear",
    ]
    assert [layer.params for layer in layers] == [320, 0, 9248, 0, 200832, 0, 1290]


def test_bias_false_and_grouped_conv() -> None:
    """bias=False and groups= change the count; both appear in real models."""
    repr_txt = """Sequential(
  (0): Conv2d(3, 64, kernel_size=(7, 7), stride=(2, 2), padding=(3, 3), bias=False)
  (1): BatchNorm2d(64, eps=1e-05, momentum=0.1, affine=True, track_running_stats=True)
  (2): Linear(in_features=64, out_features=1000, bias=False)
)"""
    assert [layer.params for layer in parse_architecture(repr_txt.splitlines())] == [
        9408,  # 64*3*7*7, no bias term
        128,  # 2*64
        64000,  # 64*1000, no bias term
    ]

    grouped = """Sequential(
  (0): Conv2d(32, 32, kernel_size=(3, 3), stride=(1, 1), padding=(1, 1), groups=32)
  (1): Conv2d(32, 64, kernel_size=(1, 1), stride=(1, 1))
  (2): GroupNorm(8, 64, eps=1e-05, affine=True)
)"""
    assert [layer.params for layer in parse_architecture(grouped.splitlines())] == [
        320,  # depthwise: 32*(32/32)*9 + 32
        2112,  # 64*32*1 + 64
        128,  # 2*64
    ]


def test_embedding_and_stacked_bidirectional_lstm() -> None:
    repr_txt = """Sequential(
  (0): Embedding(5000, 128)
  (1): LSTM(128, 256, num_layers=2, batch_first=True, bidirectional=True)
)"""
    assert [layer.params for layer in parse_architecture(repr_txt.splitlines())] == [
        640000,  # 5000*128
        2367488,  # both directions, both layers, with biases
    ]


def test_instancenorm_affine_defaults_to_off() -> None:
    """InstanceNorm has no affine parameters unless asked; BatchNorm does."""
    repr_txt = """Sequential(
  (0): LayerNorm((512,), eps=1e-05, elementwise_affine=True)
  (1): InstanceNorm2d(16, eps=1e-05, momentum=0.1, affine=False, track_running_stats=False)
  (2): InstanceNorm2d(16, eps=1e-05, momentum=0.1, affine=True, track_running_stats=False)
)"""
    assert [layer.params for layer in parse_architecture(repr_txt.splitlines())] == [
        1024,
        0,
        32,
    ]


def test_underivable_layers_report_nothing_not_zero() -> None:
    """A custom block's count is unknown — and "0" would be a false claim."""
    repr_txt = """MyNet(
  (backbone): SomeCustomBlock(hidden=64, magic=True)
  (fc): Linear(in_features=256, out_features=10, bias=True)
)"""
    layers = parse_architecture(repr_txt.splitlines())
    custom = next(layer for layer in layers if layer.layer_type == "SomeCustomBlock")
    assert custom.params_str == "", "an underivable count must not render as a number"
    known = next(layer for layer in layers if layer.layer_type == "Linear")
    assert known.params == 2570
    assert known.params_str == "2570"


def test_parameterless_layers_are_a_real_zero() -> None:
    """ReLU really does have 0 parameters — that must stay distinguishable."""
    repr_txt = """Sequential(
  (0): MaxPool2d(kernel_size=2, stride=2, padding=0, dilation=1, ceil_mode=False)
  (1): Dropout(p=0.25, inplace=False)
)"""
    for layer in parse_architecture(repr_txt.splitlines()):
        assert layer.params == 0
        assert layer.params_str == "0", "a genuine zero must not read as unknown"
