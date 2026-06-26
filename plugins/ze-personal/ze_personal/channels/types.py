from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class UserChannel:
    id: UUID
    channel_id: str          # matches InboundChannel.channel_id
    channel_type: str        # ChannelType value
    handle: str              # user's address on this channel
    display_name: str | None
    is_default_outbound: bool
    poll_enabled: bool
    created_at: datetime
