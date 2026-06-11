import io
import logging
import sys
from pathlib import Path
from typing import IO

import structlog


class _TeeStream(io.IOBase):
    """Write to multiple streams simultaneously."""

    def __init__(self, *streams: IO[str]) -> None:
        self._streams = streams

    def write(self, s: str) -> int:
        for stream in self._streams:
            stream.write(s)
        return len(s)

    def flush(self) -> None:
        for stream in self._streams:
            stream.flush()

    def writable(self) -> bool:
        return True


def configure_logging(
    level: str = "INFO",
    dev: bool = False,
    log_file: str = "",
) -> None:
    """Call once at application startup.

    When *log_file* is set the output is teed to both stdout and the file,
    which is opened in line-buffered append mode so every log line is flushed
    immediately — safe to ``tail -f`` during local development.
    """
    if dev:
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_stream: IO[str] = open(log_path, "a", buffering=1, encoding="utf-8")
        output: IO[str] = _TeeStream(sys.stdout, file_stream)
    else:
        output = sys.stdout

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.ExceptionRenderer(),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(output),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    return structlog.get_logger(name)


def bind_context(session_id: str, agent: str | None = None) -> None:
    """Bind session_id (and optionally agent) to all log records in this async context."""
    structlog.contextvars.clear_contextvars()
    ctx: dict[str, str] = {"session_id": session_id}
    if agent:
        ctx["agent"] = agent
    structlog.contextvars.bind_contextvars(**ctx)


def unbind_context() -> None:
    structlog.contextvars.clear_contextvars()
