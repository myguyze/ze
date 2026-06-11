from __future__ import annotations

import asyncio
import sys
from typing import ClassVar

from ze_core.interface.types import (
    ConfirmationRequest,
    ConfirmationResponse,
    Notification,
    OutboundMessage,
)


class CLIInterface:
    confirmation_style: ClassVar[str] = "inline"

    async def send(self, message: OutboundMessage) -> None:
        prefix = "Ze: "
        print(f"{prefix}{message.content}", flush=True)

    async def push(self, notification: Notification) -> None:
        try:
            urgency_tag = "[!] " if notification.urgency == "high" else ""
            print(f"[notification] {urgency_tag}{notification.content}", flush=True)
        except Exception:
            pass

    async def confirm(self, request: ConfirmationRequest) -> ConfirmationResponse:
        print(f"\n{request.content}")
        for i, opt in enumerate(request.options, 1):
            print(f"  {i}. {opt}")

        timeout = request.timeout_seconds

        try:
            if timeout is not None:
                raw = await asyncio.wait_for(_read_line(), timeout=timeout)
            else:
                raw = await _read_line()
        except (asyncio.TimeoutError, EOFError):
            return ConfirmationResponse(approved=False, timed_out=True)

        raw = raw.strip()
        approved = raw == "1" or raw.lower() in ("y", "yes", "approve")

        edited_content = None
        if request.editable and approved:
            print("Enter edited content (or press Enter to keep original):")
            try:
                if timeout is not None:
                    edit_raw = await asyncio.wait_for(_read_line(), timeout=timeout)
                else:
                    edit_raw = await _read_line()
                if edit_raw.strip():
                    edited_content = edit_raw.strip()
            except (asyncio.TimeoutError, EOFError):
                pass

        return ConfirmationResponse(approved=approved, edited_content=edited_content)


async def _read_line() -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, sys.stdin.readline)
