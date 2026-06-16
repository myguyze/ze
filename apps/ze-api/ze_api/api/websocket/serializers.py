from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from ze_core.messages.types import Message


def extract_thread_id(config: dict) -> str | None:
    return config.get("configurable", {}).get("thread_id")


def message_to_dict(msg: Message) -> dict:
    return {
        "id": str(msg.id),
        "role": msg.role,
        "text": msg.text,
        "components": msg.components,
        "read": msg.read,
        "thread_id": msg.thread_id,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    }


def ephemeral_assistant_message(text: str, *, components: list | None = None) -> dict:
    """Transient assistant reply (not persisted). Marked read so clients skip ack."""
    return {
        "id": str(uuid4()),
        "role": "assistant",
        "text": text,
        "components": components or [],
        "read": True,
        "thread_id": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
