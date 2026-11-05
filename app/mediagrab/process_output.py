"""Cancellation-aware line reading for subprocess output pipes."""

from __future__ import annotations

from queue import Empty, Queue
from threading import Event, Thread
from typing import TextIO, Iterator


def iter_process_output(
    stream: TextIO, cancel_event: Event, *, poll_interval: float = 0.2
) -> Iterator[str]:
    """Yield output lines while checking cancellation even when the pipe is quiet."""
    lines: Queue[str | None] = Queue()

    def read_lines() -> None:
        try:
            for line in stream:
                lines.put(line)
        finally:
            lines.put(None)

    reader = Thread(target=read_lines, daemon=True, name="mediagrab-process-output")
    reader.start()
    while reader.is_alive() or not lines.empty():
        if cancel_event.is_set():
            return
        try:
            line = lines.get(timeout=poll_interval)
        except Empty:
            continue
        if line is None:
            break
        yield line
