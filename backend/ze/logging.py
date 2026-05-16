import logging
import sys
import structlog


def configure_logging(level: str = "INFO") -> None:
    """Call once at application startup."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.ExceptionRenderer(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
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
