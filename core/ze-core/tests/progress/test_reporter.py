import asyncio


from ze_agents.progress.reporter import ProgressReporter
from ze_agents.progress.translations import ProgressTranslations


def make_reporter(data: dict) -> tuple[ProgressReporter, asyncio.Queue]:
    queue: asyncio.Queue = asyncio.Queue()

    async def _sink(text: str) -> None:
        await queue.put(text)

    t = ProgressTranslations(data=data, fallback=data)
    return ProgressReporter(t, sink=_sink), queue


async def test_emit_puts_text_on_queue():
    reporter, queue = make_reporter({"agent": {"key": "hello"}})
    await reporter.emit("agent.key")
    assert queue.get_nowait() == "hello"


async def test_emit_missing_key_does_not_put():
    reporter, queue = make_reporter({})
    await reporter.emit("missing.key")
    assert queue.empty()


async def test_emit_with_kwargs():
    reporter, queue = make_reporter({"msg": "Hi {name}"})
    await reporter.emit("msg", name="Ze")
    assert queue.get_nowait() == "Hi Ze"


async def test_emit_multiple_sequential():
    reporter, queue = make_reporter({"a": "first", "b": "second"})
    await reporter.emit("a")
    await reporter.emit("b")
    assert queue.get_nowait() == "first"
    assert queue.get_nowait() == "second"
