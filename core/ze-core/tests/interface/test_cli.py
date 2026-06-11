import asyncio
from unittest.mock import patch

import pytest

from ze_core.interface.cli import CLIInterface
from ze_core.interface.types import (
    ConfirmationRequest,
    ConfirmationResponse,
    Notification,
    OutboundMessage,
)


@pytest.fixture
def cli():
    return CLIInterface()


class TestCLISend:
    async def test_send_prints_response(self, cli, capsys):
        await cli.send(OutboundMessage(content="Hello, world!"))
        out = capsys.readouterr().out
        assert "Hello, world!" in out
        assert "Ze: " in out

    async def test_send_markdown_format(self, cli, capsys):
        await cli.send(OutboundMessage(content="**bold**", format="markdown"))
        out = capsys.readouterr().out
        assert "**bold**" in out


class TestCLIPush:
    async def test_push_prints_notification(self, cli, capsys):
        await cli.push(Notification(content="Reminder: stand-up in 5 min"))
        out = capsys.readouterr().out
        assert "[notification]" in out
        assert "Reminder: stand-up in 5 min" in out

    async def test_push_high_urgency_marks_exclamation(self, cli, capsys):
        await cli.push(Notification(content="Critical alert", urgency="high"))
        out = capsys.readouterr().out
        assert "[!]" in out

    async def test_push_swallows_errors(self, cli):
        with patch("builtins.print", side_effect=OSError("broken pipe")):
            await cli.push(Notification(content="Won't crash"))


class TestCLIConfirm:
    async def test_approve_with_1(self, cli):
        async def mock_read():
            return "1"

        with patch("ze_core.interface.cli._read_line", side_effect=mock_read):
            resp = await cli.confirm(ConfirmationRequest(
                content="Create event?", options=["Approve", "Reject"]
            ))
        assert resp.approved is True
        assert resp.timed_out is False

    async def test_reject_with_2(self, cli):
        async def mock_read():
            return "2"

        with patch("ze_core.interface.cli._read_line", side_effect=mock_read):
            resp = await cli.confirm(ConfirmationRequest(
                content="Delete file?", options=["Approve", "Reject"]
            ))
        assert resp.approved is False

    async def test_approve_with_yes(self, cli):
        async def mock_read():
            return "yes"

        with patch("ze_core.interface.cli._read_line", side_effect=mock_read):
            resp = await cli.confirm(ConfirmationRequest(
                content="Proceed?", options=["Approve", "Reject"]
            ))
        assert resp.approved is True

    async def test_timeout_returns_not_approved(self, cli):
        async def mock_read():
            await asyncio.sleep(10)
            return "1"

        with patch("ze_core.interface.cli._read_line", side_effect=mock_read):
            resp = await cli.confirm(ConfirmationRequest(
                content="Act?", options=["Approve", "Reject"], timeout_seconds=0
            ))
        assert resp.approved is False
        assert resp.timed_out is True

    async def test_eof_returns_timed_out(self, cli):
        async def mock_read():
            raise EOFError

        with patch("ze_core.interface.cli._read_line", side_effect=mock_read):
            resp = await cli.confirm(ConfirmationRequest(
                content="Act?", options=["Approve", "Reject"]
            ))
        assert resp.timed_out is True

    async def test_editable_captures_edit(self, cli):
        calls = iter(["1", "new content"])

        async def mock_read():
            return next(calls)

        with patch("ze_core.interface.cli._read_line", side_effect=mock_read):
            resp = await cli.confirm(ConfirmationRequest(
                content="Edit draft?", options=["Approve", "Reject"], editable=True
            ))
        assert resp.approved is True
        assert resp.edited_content == "new content"

    async def test_editable_empty_edit_returns_none(self, cli):
        calls = iter(["1", ""])

        async def mock_read():
            return next(calls)

        with patch("ze_core.interface.cli._read_line", side_effect=mock_read):
            resp = await cli.confirm(ConfirmationRequest(
                content="Edit draft?", options=["Approve", "Reject"], editable=True
            ))
        assert resp.approved is True
        assert resp.edited_content is None


class TestCLIConfirmationStyle:
    def test_confirmation_style_is_inline(self):
        assert CLIInterface.confirmation_style == "inline"
