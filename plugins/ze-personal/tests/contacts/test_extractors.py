from ze_personal.contacts.extractors import extract_calendar_contacts, extract_email_contacts
from ze_personal.contacts.types import SOURCE_WEIGHTS
from ze_core.orchestration.types import ToolCall


def _email_tc(result: dict, success: bool = True) -> ToolCall:
    return ToolCall(tool_name="get_email", args={}, result=result, success=success, duration_ms=0)


def _events_tc(result: list, success: bool = True) -> ToolCall:
    return ToolCall(tool_name="list_events", args={}, result=result, success=success, duration_ms=0)


def _create_tc(result: dict, success: bool = True) -> ToolCall:
    return ToolCall(tool_name="create_event", args={}, result=result, success=success, duration_ms=0)


# ── extract_email_contacts ────────────────────────────────────────────────────

def test_email_extracts_named_sender():
    tc = _email_tc({"from": "João Silva <joao@example.com>", "subject": "Hello"})
    proposals = extract_email_contacts([tc])

    assert len(proposals) == 1
    assert proposals[0].name == "João Silva"
    assert proposals[0].contact_info["email"] == "joao@example.com"


def test_email_extracts_bare_address():
    tc = _email_tc({"from": "joao@example.com", "subject": "Hi"})
    proposals = extract_email_contacts([tc])

    assert len(proposals) == 1
    assert proposals[0].contact_info["email"] == "joao@example.com"
    assert proposals[0].name  # derived from local-part


def test_email_deduplicates_same_sender():
    tc1 = _email_tc({"from": "Alice <alice@example.com>"})
    tc2 = _email_tc({"from": "Alice <alice@example.com>"})
    proposals = extract_email_contacts([tc1, tc2])

    assert len(proposals) == 1


def test_email_skips_failed_tool_calls():
    tc = _email_tc({"from": "bob@example.com"}, success=False)
    proposals = extract_email_contacts([tc])

    assert proposals == []


def test_email_skips_missing_from():
    tc = _email_tc({"subject": "No sender"})
    proposals = extract_email_contacts([tc])

    assert proposals == []


def test_email_ignores_non_email_tool_calls():
    tc = ToolCall(tool_name="list_emails", args={}, result={"from": "ignored@example.com"}, success=True, duration_ms=0)
    proposals = extract_email_contacts([tc])

    assert proposals == []


def test_email_weight_matches_source_weight():
    tc = _email_tc({"from": "x@example.com"})
    proposals = extract_email_contacts([tc])

    assert proposals[0].confidence == SOURCE_WEIGHTS["email"]


def test_email_proposals_are_unconfirmed():
    tc = _email_tc({"from": "x@example.com"})
    proposals = extract_email_contacts([tc])

    assert proposals[0].confirmed is False


def test_email_relationship_label():
    tc = _email_tc({"from": "x@example.com"})
    proposals = extract_email_contacts([tc])

    assert proposals[0].relationship == "email contact"


# ── extract_calendar_contacts ─────────────────────────────────────────────────

def test_calendar_extracts_attendees():
    event = {
        "attendees": [
            {"email": "maria@example.com", "displayName": "Maria Costa"},
            {"email": "me@example.com", "self": True},
        ]
    }
    tc = _events_tc([event])
    proposals = extract_calendar_contacts([tc])

    assert len(proposals) == 1
    assert proposals[0].name == "Maria Costa"
    assert proposals[0].contact_info["email"] == "maria@example.com"


def test_calendar_excludes_self():
    event = {"attendees": [{"email": "me@example.com", "self": True}]}
    tc = _events_tc([event])
    proposals = extract_calendar_contacts([tc])

    assert proposals == []


def test_calendar_deduplicates_across_events():
    event1 = {"attendees": [{"email": "alice@example.com", "displayName": "Alice"}]}
    event2 = {"attendees": [{"email": "alice@example.com", "displayName": "Alice"}]}
    tc = _events_tc([event1, event2])
    proposals = extract_calendar_contacts([tc])

    assert len(proposals) == 1


def test_calendar_derives_name_from_email_when_no_display_name():
    event = {"attendees": [{"email": "john.doe@example.com"}]}
    tc = _events_tc([event])
    proposals = extract_calendar_contacts([tc])

    assert proposals[0].name == "John Doe"


def test_calendar_skips_failed_tool_calls():
    tc = _events_tc([{"attendees": [{"email": "x@example.com"}]}], success=False)
    proposals = extract_calendar_contacts([tc])

    assert proposals == []


def test_calendar_handles_create_event_result():
    event = {"attendees": [{"email": "bob@example.com", "displayName": "Bob"}]}
    tc = _create_tc(event)
    proposals = extract_calendar_contacts([tc])

    assert len(proposals) == 1
    assert proposals[0].name == "Bob"


def test_calendar_weight_matches_source_weight():
    event = {"attendees": [{"email": "x@example.com"}]}
    tc = _events_tc([event])
    proposals = extract_calendar_contacts([tc])

    assert proposals[0].confidence == SOURCE_WEIGHTS["calendar"]


def test_calendar_proposals_are_unconfirmed():
    event = {"attendees": [{"email": "x@example.com"}]}
    tc = _events_tc([event])
    proposals = extract_calendar_contacts([tc])

    assert proposals[0].confirmed is False


def test_calendar_skips_events_without_attendees():
    event = {"summary": "Solo event"}
    tc = _events_tc([event])
    proposals = extract_calendar_contacts([tc])

    assert proposals == []
