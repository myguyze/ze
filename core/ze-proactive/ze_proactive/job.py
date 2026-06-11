from __future__ import annotations

from typing import Protocol, runtime_checkable

_registry: dict[str, type] = {}


@runtime_checkable
class ProactiveJob(Protocol):
    job_id: str

    async def run(self) -> None: ...


def proactive_job(cls: type) -> type:
    """Register a class as a proactive job. The class must define job_id and run()."""
    if not hasattr(cls, "job_id"):
        raise TypeError(f"{cls.__name__} must define a job_id class attribute")
    _registry[cls.job_id] = cls
    return cls


def get_registered_proactive_jobs() -> dict[str, type]:
    return dict(_registry)
