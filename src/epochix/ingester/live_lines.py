"""Lines out of a source that is still being written.

A line ends at a newline and nowhere else. A progress bar redraws itself with
carriage returns inside one line, and the pipeline reads that line in its final
state — so a live source holds what it has until the newline arrives.

One bar cannot wait: a LoRA trainer draws a single bar for the whole run and
ends no line until a checkpoint or the end of training, hours later. Its
finished redraws are handed on as they arrive
(`epochix.parsers.step_bar.finished_step_bar_redraws`); the one still being
drawn waits for its end. Every other bar waits for its newline.

The file tail, the pipe on stdin and the SSH tail all split what they read
here, so the three cannot come to read one run differently.
"""

from __future__ import annotations

import codecs

from epochix.parsers.step_bar import finished_step_bar_redraws

# Hand an un-terminated line on once it exceeds this, so a source with no
# newlines can't grow the buffer without bound. Far larger than any real log
# line.
MAX_PARTIAL = 1_048_576  # 1 MiB


def take_lines(held: str) -> tuple[list[str], str]:
    """The lines to hand on from what a live source holds, and what it keeps."""
    lines: list[str] = []
    if "\n" in held:
        *lines, held = held.split("\n")
    finished, held = finished_step_bar_redraws(held)
    if finished is not None:
        lines.append(finished)
    # A source with no newlines (a binary blob, or one giant JSON line) would
    # otherwise be held for ever. Hand it on as a line once it is clearly not
    # a normal log line.
    if len(held) > MAX_PARTIAL:
        lines.append(held)
        held = ""
    return lines, held


class LiveLines:
    """The lines of a byte stream, as its chunks arrive.

    Bytes are read as UTF-8; a character cut in two by a chunk boundary is
    completed by the next chunk rather than replaced.
    """

    def __init__(self) -> None:
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._held = ""

    def feed(self, data: bytes) -> list[str]:
        """Take a chunk; return the lines it finished."""
        lines, self._held = take_lines(self._held + self._decoder.decode(data))
        return lines

    def end(self) -> list[str]:
        """The stream closed: what is held is its last line."""
        rest = self._held + self._decoder.decode(b"", final=True)
        self._held = ""
        return [rest] if rest else []
