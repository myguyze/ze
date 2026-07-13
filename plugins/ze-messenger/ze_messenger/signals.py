from datetime import datetime
from uuid import uuid4

from ze_communication.types import InboundMessage
from ze_memory.types import EntityRef, Signal
from ze_plugin.signals import SignalSource


class MessagingSignalSource(SignalSource):
    source_key = "messaging"

    def __init__(self) -> None:
        self._buffer: list[Signal] = []

    def push(self, msg: InboundMessage) -> None:
        self._buffer.append(
            Signal(
                id=uuid4(),
                source=self.source_key,
                external_ref=msg.message_id,
                title=msg.subject or f"Message from {msg.sender}",
                summary=msg.body[:500],
                occurred_at=msg.received_at,
                entities=[EntityRef(name=msg.sender, entity_type="person")],
                magnitude=0.0,
                payload={
                    "channel_type": msg.channel_type,
                    "thread_id": msg.thread_id,
                    "sender": msg.sender,
                },
            )
        )

    async def poll(self, since: datetime) -> list[Signal]:
        signals, self._buffer = self._buffer, []
        return signals
