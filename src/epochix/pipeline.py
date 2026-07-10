"""Processing pipeline: ingestion → parse → normalize → story → store → broadcast.

This module owns the hot path for live and batch runs.  The CLI and server
both call :func:`run_pipeline` to drive the full loop.

Architecture (§6.2)::

    BaseIngester.lines()
        → parser.parse_line(line, ctx)     # RawMetric list
        → normalizer.normalize(raw)        # MetricEvent
        → story_engine.process(event)      # StoryFrame | None
        → store.append_*(…)               # durable write
        → hub.publish(run_id, msg)         # fan-out to WS/SSE clients
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from epochix.enums import TaskType
from epochix.models import Run
from epochix.normalizer import normalize
from epochix.parsers.base import ParserContext
from epochix.parsers.registry import SNIFF_SAMPLE_LINES, detect_parser
from epochix.story_engine import StoryEngine

# ANSI escape sequences (color codes + "erase line" \x1b[K, used by every
# modern "rich" CLI: ultralytics, lightning, tqdm). They land in the log
# when stdout is redirected to a file/pipe and break our regex-based parsers,
# so strip them before any downstream sees the text.
_ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def _clean_line(text: str) -> str:
    """Strip ANSI escapes and unify carriage-return progress updates into the
    final state of the line (most progress bars emit ``\\rstep1\\rstep2``;
    we only care about the last update before the actual newline)."""
    cleaned = _ANSI_RE.sub("", text)
    if "\r" in cleaned:
        cleaned = cleaned.rsplit("\r", 1)[-1]
    return cleaned


if TYPE_CHECKING:
    from epochix.ingester import BaseIngester
    from epochix.parsers.base import BaseParser
    from epochix.server.hub import Hub
    from epochix.store.sqlite_store import RunStore

logger = logging.getLogger(__name__)

# Live mode: if the stream is still buffering for the sniff window when the
# producer pauses (between epochs) for this many seconds, sniff on what we have
# and start emitting — so a run shorter than SNIFF_SAMPLE_LINES doesn't sit
# blank until it finishes. Batch file reads never pause, so they are unaffected.
IDLE_SNIFF_SECS = 1.5


def _emit_line(
    *,
    text: str,
    timestamp: datetime,
    parser: BaseParser,
    ctx: ParserContext,
    run_id: str,
    engine: StoryEngine,
    store: RunStore,
    hub: Hub,
) -> float | None:
    """Parse one log line and push any resulting frames into the store + hub.

    Returns the epoch from the last frame emitted (or None if no frame).
    """
    raw_metrics = parser.parse_line(text, ctx)

    # Keep the story engine's total-epochs hint in sync with whatever the
    # parser has discovered (e.g. "Epoch 30/30" → total_epochs=30). Without
    # this, progress estimation falls back to a constant 0.05 ("5% done").
    if ctx.total_epochs is not None and engine.total_epochs != ctx.total_epochs:
        engine.total_epochs = ctx.total_epochs

    last_epoch: float | None = None
    for raw in raw_metrics:
        try:
            event = normalize(raw, run_id=run_id, timestamp=timestamp)
        except ValueError:
            continue

        store.append_metric_event(event)

        frame = engine.process(event)
        if frame is not None:
            last_epoch = frame.epoch
            store.append_story_frame(frame)

            msg = hub.make_message(
                msg_type="story_frame",
                run_id=run_id,
                seq=frame.seq,
                payload=frame.model_dump(mode="json"),
            )
            hub.publish(run_id, msg)

            for ms in frame.milestones:
                ms_msg = hub.make_message(
                    msg_type="milestone",
                    run_id=run_id,
                    seq=ms.seq,
                    payload=ms.model_dump(mode="json"),
                )
                hub.publish(run_id, ms_msg)

    return last_epoch


async def run_pipeline(
    *,
    ingester: BaseIngester,
    run_id: str,
    store: RunStore,
    hub: Hub,
    run_name: str | None = None,
    task: TaskType | None = None,
    primary_metric: str | None = None,
    total_epochs: int | None = None,
    locale: str = "en",
    keep_raw_lines: bool = False,
    architecture: list[dict[str, object]] | None = None,
) -> Run:
    """Drive the full ingestion pipeline for one run.

    Parameters
    ----------
    ingester:
        Source of :class:`~epochix.models.RawLogLine` objects.
    run_id:
        Pre-generated ULID for this run.
    store:
        Durable SQLite store.
    hub:
        Broadcast hub for live WS/SSE clients.
    run_name:
        Human-readable run name (optional).
    task:
        Force a specific :class:`~epochix.enums.TaskType`.
        ``None`` → auto-detect after 3 metric events.
    primary_metric:
        Override the primary metric key.
    total_epochs:
        Hint for progress estimation.
    locale:
        Language code for narrative templates (default ``"en"``).
    keep_raw_lines:
        Whether to persist raw log lines to the store.

    Returns
    -------
    Run
        The completed :class:`~epochix.models.Run` object.
    """
    from epochix.config import get_settings

    settings = get_settings()

    # --- Parser auto-detection (sniff first N lines) -------------------
    sample_lines: list[str] = []
    parser: BaseParser | None = None
    ctx = ParserContext(run_id=run_id)
    engine = StoryEngine(
        run_id=run_id,
        task=task,
        primary_metric=primary_metric,
        total_epochs=total_epochs,
        locale=locale,
    )

    effective_keep = keep_raw_lines or settings.keep_raw_lines

    # Create run record
    started_at = datetime.now(tz=timezone.utc)
    run = Run(
        id=run_id,
        name=run_name,
        task_type=task or TaskType.CUSTOM,
        started_at=started_at,
        primary_metric=primary_metric or "val_loss",
        parser_used="unknown",
    )
    store.create_run(run)

    # Caller-supplied *real* architecture (e.g. LiveReporter(model=…)) — store
    # it and broadcast so the Network State panel shows the actual model
    # immediately, without needing a model summary in the log stream.
    if architecture:
        existing = store.get_run(run_id)
        cfg = existing.config if existing else {}
        store.update_run_config(run_id, {**cfg, "architecture": architecture})
        hub.publish(
            run_id,
            hub.make_message(
                msg_type="architecture",
                run_id=run_id,
                seq=-1,
                payload={"architecture": architecture},
            ),
        )

    last_seq = 0
    last_epoch: float | None = None

    # Buffer lines received before the parser is detected so we can replay
    # them.  This is critical for short log files (< SNIFF_SAMPLE_LINES lines)
    # where the sniff window never fills while streaming.
    sniff_buffer: list[tuple[int, datetime, str]] = []  # (seq, timestamp, text)

    # Collect the first 200 lines for architecture detection (model summary
    # tables always appear in the header, before training starts).
    _ARCH_SCAN_LIMIT = 200
    arch_scan_lines: list[str] = []
    arch_detected = False

    def _try_detect_architecture(*, broadcast: bool) -> bool:
        """Run architecture detection on collected header lines.

        Returns True if architecture was detected and stored. Called once
        during ingestion (as soon as enough lines have accumulated so the
        dashboard can show layers LIVE while training is still running)
        and again at end as a safety net.
        """
        try:
            from epochix.parsers.architecture_parser import parse_architecture

            arch_layers = parse_architecture(arch_scan_lines)
        except Exception:  # noqa: BLE001
            logger.debug("Architecture detection failed (non-fatal)", exc_info=True)
            return False
        if not arch_layers:
            return False
        arch_data = [layer.to_dict() for layer in arch_layers]
        existing = store.get_run(run_id)
        current_cfg = existing.config if existing else {}
        new_config = {**current_cfg, "architecture": arch_data}
        store.update_run_config(run_id, new_config)
        if broadcast:
            arch_msg = hub.make_message(
                msg_type="architecture",
                run_id=run_id,
                seq=-1,
                payload={"architecture": arch_data},
            )
            hub.publish(run_id, arch_msg)
        logger.debug(
            "Architecture detected: %d layers",
            len(arch_layers),
        )
        return True

    # Sniff on the buffered sample and replay it (idempotent once a parser is
    # set). Called when the sniff window fills, when the live stream goes idle
    # between epochs, or at end-of-stream.
    def _flush_sniff() -> None:
        nonlocal parser, run, sniff_buffer, last_epoch
        if parser is not None or not sample_lines:
            return
        parser = detect_parser(sample_lines)
        run = Run(**{**run.model_dump(), "parser_used": parser.name})
        logger.debug("Detected parser (%d lines): %s", len(sample_lines), parser.name)
        for buf_seq, buf_ts, buf_text in sniff_buffer:
            ctx.seq = buf_seq
            ep = _emit_line(
                text=buf_text,
                timestamp=buf_ts,
                parser=parser,
                ctx=ctx,
                run_id=run_id,
                engine=engine,
                store=store,
                hub=hub,
            )
            if ep is not None:
                last_epoch = ep
        sniff_buffer = []

    def _process_line(raw_line: object) -> None:
        nonlocal last_seq, arch_detected, last_epoch
        ctx.seq = raw_line.seq  # type: ignore[attr-defined]
        last_seq = raw_line.seq  # type: ignore[attr-defined]

        # Strip ANSI escapes + carriage-return progress-bar updates so the
        # downstream parsers see clean text.
        clean_text = _clean_line(raw_line.text)  # type: ignore[attr-defined]

        if len(arch_scan_lines) < _ARCH_SCAN_LIMIT:
            arch_scan_lines.append(clean_text)
            if len(arch_scan_lines) >= _ARCH_SCAN_LIMIT and not arch_detected:
                arch_detected = _try_detect_architecture(broadcast=True)

        if effective_keep:
            store.append_raw_line(
                run_id=run_id,
                seq=raw_line.seq,  # type: ignore[attr-defined]
                ts=raw_line.timestamp,  # type: ignore[attr-defined]
                text=clean_text,
            )

        if parser is None:
            sample_lines.append(clean_text)
            sniff_buffer.append(
                (raw_line.seq, raw_line.timestamp, clean_text)  # type: ignore[attr-defined]
            )
            if len(sample_lines) >= SNIFF_SAMPLE_LINES:
                _flush_sniff()
            return

        ep = _emit_line(
            text=clean_text,
            timestamp=raw_line.timestamp,  # type: ignore[attr-defined]
            parser=parser,
            ctx=ctx,
            run_id=run_id,
            engine=engine,
            store=store,
            hub=hub,
        )
        if ep is not None:
            last_epoch = ep

    # Consume the ingester with an idle timeout (see IDLE_SNIFF_SECS).
    _line_iter = ingester.lines().__aiter__()
    _done = object()

    async def _next_or_done() -> object:
        try:
            return await _line_iter.__anext__()
        except StopAsyncIteration:
            return _done

    _pending: asyncio.Future[object] | None = None
    while True:
        if _pending is None:
            _pending = asyncio.ensure_future(_next_or_done())
        try:
            item = await asyncio.wait_for(asyncio.shield(_pending), IDLE_SNIFF_SECS)
        except asyncio.TimeoutError:
            _flush_sniff()  # live stream idle → emit what we have
            continue
        _pending = None
        if item is _done:
            break
        _process_line(item)

    # Source ended before the sniff window filled — detect + replay now.
    _flush_sniff()

    # --- Architecture detection (end-of-stream fallback) ----------------
    # If the scan limit was never reached (short logs) we get one more shot
    # here. Idempotent — already-detected runs no-op.
    if not arch_detected and arch_scan_lines:
        _try_detect_architecture(broadcast=False)

    # --- Finalise -------------------------------------------------------
    final_milestones = engine.finalize(last_seq, last_epoch)
    for ms in final_milestones:
        ms_msg = hub.make_message(
            msg_type="milestone",
            run_id=run_id,
            seq=ms.seq,
            payload=ms.model_dump(mode="json"),
        )
        hub.publish(run_id, ms_msg)

    # Determine final grade from the most recent story frame
    frames = store.get_story_frames(run_id)
    last_frame = frames[-1] if frames else None
    final_grade = last_frame.grade if last_frame else None
    story_summary = last_frame.narrative if last_frame else None

    # Persist the auto-detected values the engine / parser locked in during
    # the run — they were placeholders at run creation time and must be
    # written back so the dashboard, exports and listings all show the truth.
    store.finish_run(
        run_id=run_id,
        final_grade=final_grade,
        story_summary=story_summary,
        task_type=engine.task,
        parser_used=parser.name if parser is not None else None,
        primary_metric=engine._effective_primary_key() if engine.task else None,
    )

    # Signal end-of-run to all live subscribers
    complete_msg = hub.make_message(
        msg_type="complete",
        run_id=run_id,
        seq=last_seq,
        payload={"final_grade": final_grade.value if final_grade else None},
    )
    hub.publish(run_id, complete_msg)
    hub.close_run(run_id)

    # Return the final Run record from the store
    finished_run = store.get_run(run_id)
    assert finished_run is not None
    return finished_run
