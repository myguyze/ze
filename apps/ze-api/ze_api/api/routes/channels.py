from fastapi import APIRouter, Depends, Request

from ze_api.api.dependencies import require_api_key
from ze_api.api.schemas import (
    ChannelInfo,
    ChannelListResponse,
    ChannelResponse,
    ChannelUpdateRequest,
)

router = APIRouter(prefix="/api/v0/channels", tags=["channels"])


@router.get(
    "",
    response_model=ChannelListResponse,
    summary="List connected communication channels",
    description="Returns channels Ze is connected to with poll state and last poll time.",
    operation_id="list_channels",
)
async def list_channels(
    request: Request,
    _: str = Depends(require_api_key),
) -> ChannelListResponse:
    container = request.app.state.container
    user_channel_store = container._plugin_stores.get("user_channel_store")
    watermark_store = container._plugin_stores.get("watermark_store")
    channel_registry = getattr(container, "channel_registry", None)

    if user_channel_store is None:
        return ChannelListResponse(channels=[])

    channels = await user_channel_store.list_all()
    registry_channels = (
        {c.channel_id: c for c in channel_registry.inbound_channels()}
        if channel_registry else {}
    )

    infos: list[ChannelInfo] = []
    for uc in channels:
        last_polled_at = None
        if watermark_store is not None:
            try:
                from datetime import timedelta, timezone, datetime
                candidate = await watermark_store.get(uc.channel_id)
                # Only include if it was actually set (not the default lookback)
                default_cutoff = datetime.now(timezone.utc) - timedelta(hours=25)
                if candidate > default_cutoff:
                    last_polled_at = candidate
            except Exception:
                pass

        reg_ch = registry_channels.get(uc.channel_id)
        infos.append(ChannelInfo(
            channel_id=uc.channel_id,
            channel_type=uc.channel_type,
            handle=uc.handle,
            display_name=uc.display_name,
            is_default_outbound=uc.is_default_outbound,
            poll_enabled=uc.poll_enabled,
            supports_push=reg_ch.supports_push if reg_ch is not None else False,
            last_polled_at=last_polled_at,
        ))

    return ChannelListResponse(channels=infos)


@router.patch(
    "/{channel_id}",
    response_model=ChannelResponse,
    summary="Update channel configuration",
    description="Toggle poll_enabled or set as default outbound.",
    operation_id="update_channel",
)
async def update_channel(
    channel_id: str,
    body: ChannelUpdateRequest,
    request: Request,
    _: str = Depends(require_api_key),
) -> ChannelResponse:
    container = request.app.state.container
    user_channel_store = container._plugin_stores.get("user_channel_store")
    watermark_store = container._plugin_stores.get("watermark_store")
    channel_registry = getattr(container, "channel_registry", None)

    if user_channel_store is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Channel store not available")

    if body.poll_enabled is not None:
        await user_channel_store.set_poll_enabled(channel_id, body.poll_enabled)
    if body.is_default_outbound:
        await user_channel_store.set_default_outbound(channel_id)
    if body.display_name is not None:
        await user_channel_store.set_display_name(channel_id, body.display_name)

    uc = await user_channel_store.get(channel_id)
    if uc is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Channel {channel_id!r} not found")

    last_polled_at = None
    if watermark_store is not None:
        try:
            from datetime import datetime, timedelta, timezone
            candidate = await watermark_store.get(uc.channel_id)
            default_cutoff = datetime.now(timezone.utc) - timedelta(hours=25)
            if candidate > default_cutoff:
                last_polled_at = candidate
        except Exception:
            pass

    reg_ch = None
    if channel_registry is not None:
        reg_ch = channel_registry.get_inbound_by_id(channel_id)

    return ChannelResponse(channel=ChannelInfo(
        channel_id=uc.channel_id,
        channel_type=uc.channel_type,
        handle=uc.handle,
        display_name=uc.display_name,
        is_default_outbound=uc.is_default_outbound,
        poll_enabled=uc.poll_enabled,
        supports_push=reg_ch.supports_push if reg_ch is not None else False,
        last_polled_at=last_polled_at,
    ))
