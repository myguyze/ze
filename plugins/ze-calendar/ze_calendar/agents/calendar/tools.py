import asyncio

from ze_core.orchestration.tool import ToolAccess, tool
from ze_google.auth import GoogleCredentials


@tool(access=ToolAccess.READ, description="List upcoming Google Calendar events.")
async def list_events(
    credentials: GoogleCredentials,
    calendar_id: str = "primary",
    max_results: int = 10,
    query: str = "",
) -> list:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    service = credentials.calendar()
    result = await asyncio.to_thread(
        lambda: service.events().list(
            calendarId=calendar_id,
            timeMin=now,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
            **({"q": query} if query else {}),
        ).execute()
    )
    return result.get("items", [])


@tool(access=ToolAccess.WRITE, description="Create a new Google Calendar event.")
async def create_event(
    credentials: GoogleCredentials,
    summary: str,
    start: str,
    end: str,
    description: str = "",
    location: str = "",
    calendar_id: str = "primary",
) -> dict:
    body: dict = {
        "summary": summary,
        "start": {"dateTime": start},
        "end": {"dateTime": end},
    }
    if description:
        body["description"] = description
    if location:
        body["location"] = location

    service = credentials.calendar()
    result = await asyncio.to_thread(
        lambda: service.events().insert(calendarId=calendar_id, body=body).execute()
    )
    return {"id": result.get("id"), "htmlLink": result.get("htmlLink")}


@tool(access=ToolAccess.WRITE, description="Update an existing Google Calendar event.")
async def update_event(
    credentials: GoogleCredentials,
    event_id: str,
    summary: str | None = None,
    start: str | None = None,
    end: str | None = None,
    description: str | None = None,
    calendar_id: str = "primary",
) -> dict:
    service = credentials.calendar()
    existing = await asyncio.to_thread(
        lambda: service.events().get(calendarId=calendar_id, eventId=event_id).execute()
    )
    if summary is not None:
        existing["summary"] = summary
    if start is not None:
        existing["start"] = {"dateTime": start}
    if end is not None:
        existing["end"] = {"dateTime": end}
    if description is not None:
        existing["description"] = description

    result = await asyncio.to_thread(
        lambda: service.events().update(
            calendarId=calendar_id, eventId=event_id, body=existing
        ).execute()
    )
    return {"id": result.get("id"), "htmlLink": result.get("htmlLink")}


@tool(access=ToolAccess.WRITE, description="Delete a Google Calendar event.")
async def delete_event(
    credentials: GoogleCredentials,
    event_id: str,
    calendar_id: str = "primary",
) -> None:
    service = credentials.calendar()
    await asyncio.to_thread(
        lambda: service.events().delete(
            calendarId=calendar_id, eventId=event_id
        ).execute()
    )
