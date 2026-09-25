"""EPOCHIX_SCRUB_SECRETS: documented, and until now implemented nowhere."""

from __future__ import annotations

import time

import pytest

from epochix.scrub import REDACTED, scrub_secrets


@pytest.mark.parametrize(
    ("line", "secret"),
    [
        ("export WANDB_API_KEY=a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0", "a1b2c3d4e5f6"),
        ("HF_TOKEN: hf_abcdefghijklmnopqrstuvwxyz0123456789", "hf_abcdef"),
        ('{"password": "hunter2hunter2"}', "hunter2"),
        ("db = postgresql://admin:s3cr3tpass@db.internal:5432/runs", "s3cr3tpass"),
        ("Authorization: Bearer abcdef0123456789abcdef", "abcdef0123456789"),
        ("using key AKIAIOSFODNN7EXAMPLE for s3", "AKIAIOSFODNN7EXAMPLE"),
        ("gh token ghp_0123456789abcdefghijklmnopqrstuvwxyzAB here", "ghp_0123"),
        ("OPENAI sk-proj-abcdefghijklmnopqrstuvwxyz012345", "sk-proj-abc"),
        ("anthropic_api_key=sk-ant-api03-abcdefghijklmnopqrstuvwx", "sk-ant"),
        ("aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "wJalrXUtn"),
        ("jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N", "eyJhbGci"),
    ],
)
def test_secrets_are_redacted(line: str, secret: str) -> None:
    out = scrub_secrets(line)
    assert secret not in out, out
    assert REDACTED in out


@pytest.mark.parametrize(
    "line",
    [
        "Epoch 3/10 - loss: 0.4321 - accuracy: 0.8765 - val_loss: 0.5012",
        "step=120 loss=0.5 tokens_per_sec=1234.5 lr=3e-4",
        "max_tokens=512 tokenizer=bert-base-uncased",
        "{'loss': 0.61, 'eval_accuracy': 0.87, 'epoch': 2.0}",
        "commit 4f8a2b1 author=keyvan",
        "token_count: 2048",
    ],
)
def test_training_output_is_left_alone(line: str) -> None:
    assert scrub_secrets(line) == line


def test_the_name_and_delimiter_survive() -> None:
    assert (
        scrub_secrets("HF_TOKEN=hf_abcdefghijklmnopqrstuvwxyz0123456789") == f"HF_TOKEN={REDACTED}"
    )


def test_linear_on_a_hostile_line() -> None:
    line = "api_key=" + "a" * 200_000 + " " + "x" * 200_000
    start = time.perf_counter()
    scrub_secrets(line)
    assert time.perf_counter() - start < 2.0
