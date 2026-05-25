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

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from model_story.enums import TaskType
from model_story.models import Run
from model_story.normalizer import normalize
from model_story.parsers.base import ParserContext
from model_story.parsers.registry import SNIFF_SAMPLE_LINES, detect_parser
from model_story.story_engine import StoryEngine

if TYPE_CHECKING:
    from model_story.ingester import BaseIngester
    from model_story.parsers.base import BaseParser
    from model_story.server.hub import Hub
    from model_story.store.sqlite_store import RunStore

logger = logging.getLogger(__name__)


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
) -> Run:
    """Drive the full ingestion pipeline for one run.

    Parameters
    ----------
    ingester:
        Source of :class:`~model_story.models.RawLogLine` objects.
    run_id:
        Pre-generated ULID for this run.
    store:
        Durable SQLite store.
    hub:
        Broadcast hub for live WS/SSE clients.
    run_name:
        Human-readable run name (optional).
    task:
        Force a specific :class:`~model_story.enums.TaskType`.
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
        The completed :class:`~model_story.models.Run` object.
    """
    from model_story.config import get_settings

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

    async for raw_line in ingester.lines():
        ctx.seq = raw_line.seq
        last_seq = raw_line.seq

        # Collect lines for architecture parsing (first 200 only)
        if len(arch_scan_lines) < _ARCH_SCAN_LIMIT:
            arch_scan_lines.append(raw_line.text)

        if effective_keep:
            store.append_raw_line(
                run_id=run_id,
                seq=raw_line.seq,
                ts=raw_line.timestamp,
                text=raw_line.text,
            )

        if parser is None:
            # Still collecting the sniff window.
            sample_lines.append(raw_line.text)
            sniff_buffer.append((raw_line.seq, raw_line.timestamp, raw_line.text))

            if len(sample_lines) >= SNIFF_SAMPLE_LINES:
                # Sniff window full — detect and replay.
                parser = detect_parser(sample_lines)
                run = Run(**{**run.model_dump(), "parser_used": parser.name})
                logger.debug("Detected parser: %s", parser.name)
                for buf_seq, buf_ts, buf_text in sniff_buffer:
                    ctx.seq = buf_seq
                    epoch = _emit_line(
                        text=buf_text,
                        timestamp=buf_ts,
                        parser=parser,
                        ctx=ctx,
                        run_id=run_id,
                        engine=engine,
                        store=store,
                        hub=hub,
                    )
                    if epoch is not None:
                        last_epoch = epoch
                sniff_buffer = []
            # Line handled (buffered or replayed) — move to next.
            continue

        # Normal path: parser already known.
        epoch = _emit_line(
            text=raw_line.text,
            timestamp=raw_line.timestamp,
            parser=parser,
            ctx=ctx,
            run_id=run_id,
            engine=engine,
            store=store,
            hub=hub,
        )
        if epoch is not None:
            last_epoch = epoch

    # If the source ended before the sniff window filled (e.g. short batch
    # files), detect the parser now and replay the buffered lines.
    if parser is None and sample_lines:
        parser = detect_parser(sample_lines)
        run = Run(**{**run.model_dump(), "parser_used": parser.name})
        logger.debug(
            "Detected parser (late, %d lines): %s", len(sample_lines), parser.name
        )
        for buf_seq, buf_ts, buf_text in sniff_buffer:
            ctx.seq = buf_seq
            epoch = _emit_line(
                text=buf_text,
                timestamp=buf_ts,
                parser=parser,
                ctx=ctx,
                run_id=run_id,
                engine=engine,
                store=store,
                hub=hub,
            )
            if epoch is not None:
                last_epoch = epoch

    # --- Detect model architecture (from header lines) -------------------
    try:
        from model_story.parsers.architecture_parser import parse_architecture
        arch_layers = parse_architecture(arch_scan_lines)
        if arch_layers:
            arch_data = [layer.to_dict() for layer in arch_layers]
            new_config = {**run.config, "architecture": arch_data}
            run = Run(**{**run.model_dump(), "config": new_config})
            store.update_run_config(run_id, new_config)
            logger.debug(
                "Architecture detected: %d layers (%s)",
                len(arch_layers),
                ", ".join(f"{lyr.name}({lyr.layer_type})" for lyr in arch_layers),
            )
    except Exception:
        logger.debug("Architecture detection failed (non-fatal)", exc_info=True)

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

    store.finish_run(
        run_id=run_id,
        final_grade=final_grade,
        story_summary=story_summary,
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
