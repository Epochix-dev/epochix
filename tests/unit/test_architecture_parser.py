"""Architecture-detection tests across all supported summary formats."""
from __future__ import annotations

from epochix.parsers.architecture_parser import (
    _classify,
    parse_architecture,
)

# ── layer-type → visual classification ─────────────────────────────────────────

class TestClassify:
    def test_recurrent_family(self) -> None:
        for t in ("LSTM", "GRU", "RNN", "BiLSTM", "bilstm", "LSTMCell"):
            assert _classify(t)["visual_type"] == "recurrent"

    def test_attention_family(self) -> None:
        for t in ("MultiheadAttention", "TransformerEncoderLayer", "BertLayer",
                  "GPT2Block", "SelfAttention", "LlamaDecoderLayer"):
            assert _classify(t)["visual_type"] == "attention"

    def test_conv_family(self) -> None:
        for t in ("Conv2d", "ResNet50", "EfficientNet", "MobileNetV3",
                  "ConvTranspose2d", "C2f", "Bottleneck"):
            assert _classify(t)["visual_type"] == "conv"

    def test_dense_family(self) -> None:
        for t in ("Linear", "Dense", "Embedding", "Classifier"):
            assert _classify(t)["visual_type"] == "dense"

    def test_norm_family(self) -> None:
        for t in ("BatchNorm2d", "LayerNorm", "Dropout", "MaxPool2d", "RMSNorm"):
            assert _classify(t)["visual_type"] == "norm"

    def test_unknown_is_generic(self) -> None:
        meta = _classify("SomeWeirdCustomThing")
        assert meta["visual_type"] == "generic"
        assert meta["tech_label"] == "LAYER"

    def test_yolo_detect_head(self) -> None:
        assert _classify("Detect")["tech_label"] == "DETECT"


# ── format detection ───────────────────────────────────────────────────────────

class TestPyTorchLightning:
    def test_parses_pl_table(self) -> None:
        lines = [
            "  | Name    | Type     | Params",
            "-----------------------------------",
            "0 | encoder | ResNet50 | 23.5 M",
            "1 | lstm    | LSTM     | 8.4 M",
            "2 | head    | Linear   | 2.1 K",
            "-----------------------------------",
        ]
        layers = parse_architecture(lines)
        assert [lyr.layer_type for lyr in layers] == ["ResNet50", "LSTM", "Linear"]
        assert layers[1].visual_type == "recurrent"
        assert layers[0].params == 23_500_000


class TestKerasSummary:
    def test_classic_summary(self) -> None:
        lines = [
            'Model: "sequential"',
            "_________________________________________________________________",
            " Layer (type)                Output Shape              Param #",
            "=================================================================",
            " conv2d (Conv2D)             (None, 26, 26, 32)        320",
            " max_pooling2d (MaxPooling2D)(None, 13, 13, 32)        0",
            " flatten (Flatten)           (None, 5408)              0",
            " dense (Dense)               (None, 128)               692352",
            " dense_1 (Dense)             (None, 10)                1290",
            "=================================================================",
            "Total params: 693,962",
        ]
        layers = parse_architecture(lines)
        types = [lyr.layer_type for lyr in layers]
        # Flatten (trivial) is dropped; conv/pool/dense remain.
        assert "Conv2D" in types
        assert "Dense" in types
        assert "Flatten" not in types
        dense = next(lyr for lyr in layers if lyr.layer_type == "Dense")
        assert dense.params == 692352

    def test_keras3_box_summary(self) -> None:
        lines = [
            "┏━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┓",
            "┃ Layer (type)       ┃ Output Shape      ┃    Param # ┃",
            "┡━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━┩",
            "│ conv2d (Conv2D)    │ (None, 26, 26, 32)│        320 │",
            "│ dense (Dense)      │ (None, 10)        │      1,290 │",
            "└────────────────────┴───────────────────┴────────────┘",
            " Total params: 1,610",
        ]
        layers = parse_architecture(lines)
        assert [lyr.layer_type for lyr in layers] == ["Conv2D", "Dense"]
        assert layers[1].params == 1290


class TestTorchinfo:
    def test_torchinfo_tree(self) -> None:
        lines = [
            "==========================================================",
            "Layer (type:depth-idx)         Output Shape      Param #",
            "==========================================================",
            "├─Conv2d: 1-1                  [1, 32, 26, 26]    320",
            "├─LSTM: 1-2                    [1, 128]           8,400",
            "├─Linear: 1-3                  [1, 10]            1,290",
            "==========================================================",
            "Total params: 10,010",
        ]
        layers = parse_architecture(lines)
        assert [lyr.layer_type for lyr in layers] == ["Conv2d", "LSTM", "Linear"]
        assert layers[1].visual_type == "recurrent"
        assert layers[2].params == 1290

    def test_torchsummary_flat(self) -> None:
        lines = [
            "----------------------------------------------------------------",
            "        Layer (type)               Output Shape         Param #",
            "================================================================",
            "            Conv2d-1         [-1, 32, 26, 26]             320",
            "            Linear-2                  [-1, 10]           1,290",
            "================================================================",
        ]
        layers = parse_architecture(lines)
        assert [lyr.layer_type for lyr in layers] == ["Conv2d", "Linear"]


class TestModuleRepr:
    def test_print_model_repr_with_bilstm(self) -> None:
        lines = [
            "SeqClassifier(",
            "  (embedding): Embedding(10000, 300)",
            "  (lstm): LSTM(300, 256, num_layers=2, bidirectional=True)",
            "  (fc): Linear(in_features=512, out_features=5, bias=True)",
            ")",
        ]
        layers = parse_architecture(lines)
        types = [lyr.layer_type for lyr in layers]
        assert types[0] == "Embedding"
        assert types[1] == "BiLSTM"  # bidirectional=True relabelled
        assert layers[1].visual_type == "recurrent"
        assert types[2] == "Linear"


class TestRobustness:
    def test_empty_and_garbage(self) -> None:
        assert parse_architecture([]) == []
        assert parse_architecture(["no architecture here", "loss=0.5"]) == []

    def test_caps_deep_models(self) -> None:
        # A 40-layer torchinfo dump should be capped.
        lines = ["Layer (type:depth-idx)  Output Shape  Param #"]
        lines += [f"├─Conv2d: 1-{i}   [1, 8, 8, 8]   {i * 10}" for i in range(40)]
        layers = parse_architecture(lines)
        assert 0 < len(layers) <= 24


class TestUltralyticsYolo:
    def test_verbose_layer_table(self) -> None:
        lines = [
            "                   from  n    params  module                          arguments",
            "  0                  -1  1       928  ultralytics.nn.modules.conv.Conv [3, 32, 3, 2]",
            "  9                  -1  1    460288  ultralytics.nn.modules.block.SPPF [256, 256, 5]",
            " 22        [15, 18, 21]  1    751507  ultralytics.nn.modules.head.Detect [80]",
        ]
        layers = parse_architecture(lines)
        types = [lyr.layer_type for lyr in layers]
        assert types == ["Conv", "SPPF", "Detect"]
        assert layers[-1].tech_label == "DETECT"
        assert layers[0].params == 928

    def test_summary_line_fallback(self) -> None:
        lines = ["Ultralytics YOLOv8n summary: 225 layers, 3157200 parameters"]
        layers = parse_architecture(lines)
        assert len(layers) == 1
        assert layers[0].layer_type == "YOLOv8n"
        assert layers[0].params == 3_157_200
        assert layers[0].visual_type == "conv"


class TestDownsamplePreservesEnds:
    def test_first_and_last_kept(self) -> None:
        lines = ["Layer (type:depth-idx)  Output Shape  Param #"]
        lines += ["├─Conv2d: 1-0   [1, 8, 8, 8]   1"]
        lines += [f"├─Conv2d: 1-{i}   [1, 8, 8, 8]   {i}" for i in range(1, 39)]
        lines += ["├─Linear: 1-99   [1, 10]   999"]  # the head/output
        layers = parse_architecture(lines)
        assert len(layers) <= 24
        assert layers[-1].layer_type == "Linear"  # last (head) preserved
