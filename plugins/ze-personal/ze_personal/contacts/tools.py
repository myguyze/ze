import time
from uuid import UUID

from ze_core.channels.types import ChannelHandle, ChannelType
from ze_personal.contacts.channel_store import ContactChannelStore
from ze_core.logging import get_logger
from ze_core.orchestration.tool import ToolAccess, tool
from ze_core.orchestration.types import ToolCall

log = get_logger(__name__)


@tool(access=ToolAccess.READ, description="Get all known communication channel handles (email, LinkedIn, etc.) for a contact.")
async def get_contact_channels(
    contact_id: str,
    contact_channel_store: ContactChannelStore,
) -> ToolCall:
    args = {"contact_id": contact_id}
    start = time.monotonic()
    try:
        handles = await contact_channel_store.get_handles(UUID(contact_id))
        result = [
            {
                "channel_type": h.channel_type.value,
                "handle": h.handle,
                "preferred": h.preferred,
                "verified": h.verified,
            }
            for h in handles
        ]
        return ToolCall(
            tool_name="get_contact_channels",
            args=args,
            result=result,
            duration_ms=int((time.monotonic() - start) * 1000),
            success=True,
        )
    except Exception as exc:
        log.warning("get_contact_channels_failed", error=str(exc))
        return ToolCall(
            tool_name="get_contact_channels",
            args=args,
            result=[],
            duration_ms=int((time.monotonic() - start) * 1000),
            success=False,
            error=str(exc),
        )


@tool(access=ToolAccess.WRITE, description="Add or update a communication channel handle for a contact.")
async def set_contact_channel(
    contact_id: str,
    channel_type: str,
    handle: str,
    contact_channel_store: ContactChannelStore,
    preferred: bool = False,
) -> ToolCall:
    args = {"contact_id": contact_id, "channel_type": channel_type, "handle": handle}
    start = time.monotonic()
    try:
        ch = ChannelHandle(
            channel_type=ChannelType(channel_type),
            handle=handle,
            preferred=preferred,
        )
        await contact_channel_store.upsert(UUID(contact_id), ch)
        return ToolCall(
            tool_name="set_contact_channel",
            args=args,
            result={"status": "ok", "channel_type": channel_type, "handle": handle},
            duration_ms=int((time.monotonic() - start) * 1000),
            success=True,
        )
    except Exception as exc:
        log.warning("set_contact_channel_failed", error=str(exc))
        return ToolCall(
            tool_name="set_contact_channel",
            args=args,
            result=None,
            duration_ms=int((time.monotonic() - start) * 1000),
            success=False,
            error=str(exc),
        )
