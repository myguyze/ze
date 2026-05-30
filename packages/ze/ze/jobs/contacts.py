from ze_core.contacts.store import PersonStore
from ze.logging import get_logger
from ze_core.proactive.job import proactive_job
from ze_core.proactive.notifier import ProactiveNotifier
from ze_core.telemetry.context import set_flow_context
from ze_core.interface.types import Action, Notification


@proactive_job
class ContactReviewNotifier:
    job_id = "contact_review"
    def __init__(
        self,
        person_store: PersonStore,
        notifier: ProactiveNotifier,
    ) -> None:
        self._person_store = person_store
        self._notifier = notifier
        self._log = get_logger(__name__)

    async def run(self) -> None:
        set_flow_context("contact_review")
        pending = await self._person_store.get_pending()
        if not pending:
            self._log.debug("contact_review_nothing_pending")
            return

        for person, sources in pending:
            lines = [f"👤 New contact found: <b>{person.name}</b>"]
            if person.relationship_to_user:
                lines.append(f"Relationship: {person.relationship_to_user}")
            if person.classification and person.classification != "unknown":
                lines.append(f"Classification: {person.classification}")
            if sources:
                first_source = sources[0]
                if first_source.raw_context:
                    snippet = first_source.raw_context[:100]
                    if len(first_source.raw_context) > 100:
                        snippet += "…"
                    lines.append(f'Context: "<i>{snippet}</i>"')
            lines.append("\nAdd to your contacts?")

            pid = str(person.id)
            await self._notifier.push_notification(
                Notification(
                    content="\n".join(lines),
                    format="html",
                    actions=[
                        Action(label="Add", payload=f"contact:confirm:{pid}"),
                        Action(label="Skip", payload=f"contact:dismiss:{pid}"),
                    ],
                )
            )

        self._log.info("contact_review_pushed", count=len(pending))
