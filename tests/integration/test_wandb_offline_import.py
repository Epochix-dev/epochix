"""Reading a W&B run off local disk — no account, no key, no network.

`import_wandb` talks to the W&B API and so needs credentials, which put the
strongest thing epochix can say to a W&B user ("point it at the runs you
already have") behind a login. `import_wandb_dir` reads the run directory
instead.

The fixture is a REAL file: produced by `wandb.init()` under
`WANDB_MODE=offline`, not hand-written. The layout was not what it looked like
from the outside — there is no `wandb-summary.json` and no `output.log`, the
history lives only in the binary `run-*.wandb`, and history items carry their
name in `nested_key` rather than `key`. A fabricated fixture would have encoded
those wrong assumptions and passed.
"""

from __future__ import annotations

import zlib
from pathlib import Path

import pytest

pytest.importorskip("wandb", reason="the records are wandb's own protobuf messages")

from epochix.integrations.wandb_import import (  # noqa: E402
    _BLOCK_LEN,
    _REC_HEADER,
    _TYPE_CRC,
    _scan_wandb_file,
    _wandb_records,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "wandb_offline"
RUN_FILE = FIXTURE / "run-bx0dl6kg.wandb"


def test_fixture_is_present() -> None:
    """Guard the guard — a missing fixture must fail, not silently skip."""
    assert RUN_FILE.is_file(), f"missing fixture: {RUN_FILE}"


def test_reads_the_full_history_without_credentials() -> None:
    name, rows = _scan_wandb_file(RUN_FILE)

    assert name == "offline-run"
    # The run logged 12 epochs.
    assert len(rows) == 12
    assert rows[0] == pytest.approx({"val_accuracy": 0.445, "train_loss": 1.49, "epoch": 1.0})
    assert rows[-1]["epoch"] == 12.0
    assert rows[-1]["val_accuracy"] == pytest.approx(0.94)


def test_bookkeeping_columns_are_not_imported_as_metrics() -> None:
    """`_step`, `_runtime` and `_timestamp` are W&B internals, not results.

    Importing them would put a wall-clock timestamp on the chart as though it
    were something the model achieved.
    """
    _, rows = _scan_wandb_file(RUN_FILE)
    for row in rows:
        assert not [k for k in row if k.startswith("_")], row


def test_epoch_is_carried_through() -> None:
    """Without an epoch the dashboard shows "Epoch —" and a dead progress bar."""
    _, rows = _scan_wandb_file(RUN_FILE)
    assert [r["epoch"] for r in rows] == [float(i) for i in range(1, 13)]


# ── The framing reader ──────────────────────────────────────────────────────
#
# wandb 0.30 deleted the Python reader this importer used
# (wandb.sdk.internal.datastore), so on every current install the import told
# people who had wandb to install it. The framing is now read here; these
# tests pin the parts of the LevelDB log format the 5 KB fixture is too small
# to reach.


def _payloads() -> list[bytes]:
    return list(_wandb_records(RUN_FILE))


def _frame(kind: int, data: bytes) -> bytes:
    crc = zlib.crc32(data, _TYPE_CRC[kind]) & 0xFFFFFFFF
    return _REC_HEADER.pack(crc, len(data), kind) + data


def _reframe(payloads: list[bytes], chunk: int) -> tuple[bytes, int]:
    """The same real records, laid out as LevelDB's log writer lays them out:
    each split into FIRST/MIDDLE/LAST fragments of at most `chunk` bytes and
    at every 32 KiB block boundary, with a block trailer too short for a
    header zero-padded."""
    out = bytearray(RUN_FILE.read_bytes()[:7])  # the real file header
    pads = 0
    for payload in payloads:
        rest = payload
        begin = True
        while True:
            left = _BLOCK_LEN - len(out) % _BLOCK_LEN
            if left < _REC_HEADER.size:
                out += bytes(left)
                pads += 1
                left = _BLOCK_LEN
            piece, rest = (
                rest[: min(chunk, left - _REC_HEADER.size)],
                rest[min(chunk, left - _REC_HEADER.size) :],
            )
            last = not rest
            kind = (1 if last else 2) if begin else (4 if last else 3)
            out += _frame(kind, piece)
            begin = False
            if last:
                break
    return bytes(out), pads


def test_reader_sees_every_record_of_the_real_file() -> None:
    payloads = _payloads()
    # A run record, 12 history records and the rest of wandb's bookkeeping.
    assert len(payloads) > 12
    assert all(payloads)


def test_fragmented_records_reassemble(tmp_path: Path) -> None:
    """Records larger than what is left of a block are split FIRST/MIDDLE/LAST.
    Reading the fragments as separate records would parse garbage protobufs."""
    payloads = _payloads()
    path = tmp_path / "run-frag.wandb"
    path.write_bytes(_reframe(payloads, chunk=5)[0])
    assert _payloads() == list(_wandb_records(path))
    assert _scan_wandb_file(path) == _scan_wandb_file(RUN_FILE)


def test_block_trailer_padding_is_skipped(tmp_path: Path) -> None:
    """A record header never straddles a 32 KiB block; the gap is zero padding.
    Enough copies of the real history to cross several block boundaries."""
    payloads = _payloads() * 40
    # Find a fragment size that leaves a trailer too short for a header at
    # least once, so the padding path is really taken.
    blob, pads = next(
        (b, n) for b, n in (_reframe(payloads, chunk=c) for c in range(90, 400)) if n > 0
    )
    assert len(blob) > 3 * _BLOCK_LEN, "the fixture must actually cross blocks"
    assert pads > 0
    path = tmp_path / "run-big.wandb"
    path.write_bytes(blob)
    assert list(_wandb_records(path)) == payloads


def test_a_run_still_being_written_reads_up_to_its_last_whole_record(
    tmp_path: Path,
) -> None:
    """A RUNNING job's file ends mid-record. That tail is not a result yet —
    drop it, keep everything before it, and do not raise."""
    blob = RUN_FILE.read_bytes()
    full = _scan_wandb_file(RUN_FILE)[1]
    for cut in range(len(blob) - 1, 7, -97):
        path = tmp_path / "run-live.wandb"
        path.write_bytes(blob[:cut])
        _, rows = _scan_wandb_file(path)
        assert rows == full[: len(rows)], f"cut at {cut} changed an earlier row"


def test_corruption_raises_instead_of_inventing_numbers(tmp_path: Path) -> None:
    blob = bytearray(RUN_FILE.read_bytes())
    blob[len(blob) // 2] ^= 0xFF
    path = tmp_path / "run-bad.wandb"
    path.write_bytes(bytes(blob))
    with pytest.raises(ValueError, match="checksum"):
        _scan_wandb_file(path)


def test_a_file_that_is_not_a_wandb_run_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "run-nope.wandb"
    path.write_bytes(b"epoch 1 loss 0.5\n")
    with pytest.raises(ValueError, match="not a W&B run file"):
        _scan_wandb_file(path)


def test_a_wandb_directory_becomes_a_graded_story(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole journey: the real run directory in, a stored story out.

    Every test above stops at the reader, which is how the dead DataStore
    import went unnoticed: nothing ran the importer against a current wandb.
    """
    import socket

    from epochix.integrations.wandb_import import import_wandb_dir
    from epochix.store.sqlite_store import RunStore

    db = str(tmp_path / "runs.db")
    monkeypatch.setenv("EPOCHIX_DB", db)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    ids = import_wandb_dir(FIXTURE, port=port, open_browser=False)
    assert len(ids) == 1

    store = RunStore(db_path=db)
    run = store.get_run(ids[0])
    assert run is not None
    assert run.name == "offline-run"
    assert run.primary_metric == "val_accuracy"

    frames = store.get_story_frames(ids[0])
    assert [f.epoch for f in frames] == [float(i) for i in range(1, 13)]
    assert frames[-1].primary_metric_value == pytest.approx(0.94)
    assert frames[-1].grade.value not in ("I", "F")
