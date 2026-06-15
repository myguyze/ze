from __future__ import annotations

from fastapi import APIRouter, Request

from ze_api.api.schemas import ContactListItem

router = APIRouter(tags=["contacts"])


@router.get(
    "/api/contacts",
    response_model=list[ContactListItem],
    summary="List contacts",
    description="Returns confirmed contacts for the web client contacts screen.",
)
async def list_contacts(request: Request) -> list[ContactListItem]:
    store = request.app.state.container._plugin_stores.get("person_store")
    if store is None:
        return []

    people = await store.list_confirmed()
    return [
        ContactListItem(
            id=person.id,
            name=person.name,
            email=person.contact_info.get("email") or None,
            notes=person.notes or None,
        )
        for person in people
        if person.id is not None
    ]
