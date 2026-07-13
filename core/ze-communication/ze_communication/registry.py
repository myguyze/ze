from ze_communication.channel import Channel, InboundChannel
from ze_communication.types import ChannelType
from ze_agents.errors import ChannelNotFoundError


class ChannelRegistry:
    def __init__(self, channels: list[Channel]) -> None:
        self._channels: dict[ChannelType, Channel] = {
            c.channel_type: c for c in channels
        }
        self._inbound: dict[str, InboundChannel] = {
            c.channel_id: c for c in channels if isinstance(c, InboundChannel)
        }

    def get(self, channel_type: ChannelType) -> Channel:
        try:
            return self._channels[channel_type]
        except KeyError:
            raise ChannelNotFoundError(f"No channel registered for {channel_type!r}")

    def get_inbound(self, channel_type: ChannelType) -> InboundChannel | None:
        ch = self._channels.get(channel_type)
        return ch if isinstance(ch, InboundChannel) else None

    def available(self) -> list[ChannelType]:
        return list(self._channels.keys())

    def inbound_channels(self) -> list[InboundChannel]:
        """All registered inbound instances (all accounts, all types)."""
        return list(self._inbound.values())

    def get_inbound_by_id(self, channel_id: str) -> InboundChannel | None:
        return self._inbound.get(channel_id)
