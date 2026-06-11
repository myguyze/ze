from ze_core.channels.base import Channel
from ze_core.channels.types import ChannelType
from ze_core.errors import ChannelNotFoundError


class ChannelRegistry:
    def __init__(self, channels: list[Channel]) -> None:
        self._channels: dict[ChannelType, Channel] = {c.channel_type: c for c in channels}

    def get(self, channel_type: ChannelType) -> Channel:
        try:
            return self._channels[channel_type]
        except KeyError:
            raise ChannelNotFoundError(f"No channel registered for {channel_type!r}")

    def available(self) -> list[ChannelType]:
        return list(self._channels.keys())
