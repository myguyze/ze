from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from ze_personal.contacts.types import Person, PersonSource
from ze_personal.jobs.contacts import ContactReviewNotifier


def _make_person(**kwargs) -> Person:
    defaults = dict(
        id=uuid4(),
        name="João Silva",
        classification="professional",
        relationship_to_user="charter operator",
        contact_info={},
        confirmed=False,
        dismissed=False,
        confidence=0.9,
    )
    defaults.update(kwargs)
    return Person(**defaults)


def _make_source(person_id, raw_context="Met at Lisbon airport conference") -> PersonSource:
    return PersonSource(
        id=uuid4(),
        person_id=person_id,
        source_type="conversation",
        weight=1.0,
        raw_context=raw_context,
    )


async def test_run_does_nothing_when_no_pending():
    store = AsyncMock()
    store.get_pending = AsyncMock(return_value=[])
    notifier = AsyncMock()

    reviewer = ContactReviewNotifier(person_store=store, notifier=notifier)
    await reviewer.run()

    notifier.push_notification.assert_not_called()


async def test_run_pushes_one_message_per_pending():
    p1 = _make_person(name="Alice")
    p2 = _make_person(name="Bob")
    store = AsyncMock()
    store.get_pending = AsyncMock(return_value=[
        (p1, [_make_source(p1.id)]),
        (p2, [_make_source(p2.id)]),
    ])
    notifier = AsyncMock()

    reviewer = ContactReviewNotifier(person_store=store, notifier=notifier)
    await reviewer.run()

    assert notifier.push_notification.call_count == 2


async def test_run_message_contains_name_and_relationship():
    person = _make_person(name="Maria Costa", relationship_to_user="aviation lawyer")
    store = AsyncMock()
    store.get_pending = AsyncMock(return_value=[(person, [_make_source(person.id)])])
    notifier = AsyncMock()

    reviewer = ContactReviewNotifier(person_store=store, notifier=notifier)
    await reviewer.run()

    notif = notifier.push_notification.call_args[0][0]
    assert "Maria Costa" in notif.content
    assert "aviation lawyer" in notif.content


async def test_run_message_contains_context_snippet():
    person = _make_person()
    source = _make_source(person.id, raw_context="discussed charter pricing in detail")
    store = AsyncMock()
    store.get_pending = AsyncMock(return_value=[(person, [source])])
    notifier = AsyncMock()

    reviewer = ContactReviewNotifier(person_store=store, notifier=notifier)
    await reviewer.run()

    notif = notifier.push_notification.call_args[0][0]
    assert "discussed charter pricing" in notif.content


async def test_run_message_truncates_long_context():
    person = _make_person()
    long_context = "x" * 200
    source = _make_source(person.id, raw_context=long_context)
    store = AsyncMock()
    store.get_pending = AsyncMock(return_value=[(person, [source])])
    notifier = AsyncMock()

    reviewer = ContactReviewNotifier(person_store=store, notifier=notifier)
    await reviewer.run()

    notif = notifier.push_notification.call_args[0][0]
    assert "…" in notif.content


async def test_run_passes_keyboard_with_correct_person_id():
    person = _make_person()
    store = AsyncMock()
    store.get_pending = AsyncMock(return_value=[(person, [])])
    notifier = AsyncMock()

    reviewer = ContactReviewNotifier(person_store=store, notifier=notifier)
    await reviewer.run()

    notif = notifier.push_notification.call_args[0][0]
    assert any(str(person.id) in a.payload for a in notif.actions)


async def test_run_omits_classification_when_unknown():
    person = _make_person(classification="unknown")
    store = AsyncMock()
    store.get_pending = AsyncMock(return_value=[(person, [])])
    notifier = AsyncMock()

    reviewer = ContactReviewNotifier(person_store=store, notifier=notifier)
    await reviewer.run()

    notif = notifier.push_notification.call_args[0][0]
    assert "unknown" not in notif.content
    assert "Classification:" not in notif.content
