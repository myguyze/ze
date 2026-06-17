from __future__ import annotations

from ze_proactive.job import proactive_job

from ze_correlation.push import CorrelationPushConsumer


@proactive_job
class CorrelationJob:
    job_id = "correlation_scan"

    def __init__(self, push_consumer: CorrelationPushConsumer) -> None:
        self._consumer = push_consumer

    async def run(self) -> None:
        await self._consumer.run_once()
