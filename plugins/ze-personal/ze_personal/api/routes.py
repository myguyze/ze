from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ze_personal.api.schemas import ContactListItem, PluginPageResponse
from ze_personal.ui.page import build_contacts_page
from ze_plugin.api_auth import require_api_key

router = APIRouter(prefix="/api/v0", tags=["contacts"], dependencies=[Depends(require_api_key)])


def _page_title(count: int) -> str:
    if count == 0:
        return "People"
    if count == 1:
        return "1 person"
    return f"{count} people"


@router.get(
    "/contacts",
    response_model=list[ContactListItem],
    operation_id="listContacts",
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


@router.get(
    "/contacts/page",
    response_model=PluginPageResponse,
    operation_id="getContactsPage",
    summary="Contacts overview page",
    description="Returns the server-driven UI tree for the contacts management screen.",
)
async def get_contacts_page(request: Request) -> PluginPageResponse:
    store = request.app.state.container._plugin_stores.get("person_store")
    if store is None:
        return PluginPageResponse(title="People", tree=build_contacts_page([]))

    people = [p for p in await store.list_confirmed() if p.id is not None]
    return PluginPageResponse(
        title=_page_title(len(people)),
        tree=build_contacts_page(people),
    )
