import asyncio
from dataclasses import dataclass, field


@dataclass
class _SessionEntry:
    active: bool = False
    awaiting_edit_reply: bool = False
    pending_config: dict | None = None
    confirm_task: asyncio.Task | None = None
    pending_plan: list | None = None       # list[WorkflowStep] for dynamic plan approval
    plan_task: asyncio.Task | None = None  # approval timeout task
    awaiting_goal_redirect: str | None = None  # gate_id string when waiting for redirect text


class ActiveSessionStore:
    """Tracks in-flight graph invocations and ForceReply state per chat_id.

    State is in-memory only. On server restart, a new message from the user
    will be processed normally — the graph state survives via Postgres.
    """

    def __init__(self) -> None:
        self._sessions: dict[int, _SessionEntry] = {}

    def _get(self, chat_id: int) -> _SessionEntry:
        if chat_id not in self._sessions:
            self._sessions[chat_id] = _SessionEntry()
        return self._sessions[chat_id]

    def is_active(self, chat_id: int) -> bool:
        return self._get(chat_id).active

    def mark_active(self, chat_id: int) -> None:
        self._get(chat_id).active = True

    def clear_active(self, chat_id: int) -> None:
        self._get(chat_id).active = False

    def set_pending_confirmation(
        self,
        chat_id: int,
        config: dict,
        timeout_task: asyncio.Task,
    ) -> None:
        entry = self._get(chat_id)
        entry.pending_config = config
        entry.confirm_task = timeout_task

    def get_pending_config(self, chat_id: int) -> dict | None:
        return self._get(chat_id).pending_config

    def cancel_confirm_task(self, chat_id: int) -> None:
        entry = self._get(chat_id)
        if entry.confirm_task:
            entry.confirm_task.cancel()
            entry.confirm_task = None
        entry.pending_config = None

    def set_awaiting_edit(self, chat_id: int) -> None:
        self._get(chat_id).awaiting_edit_reply = True

    def is_awaiting_edit(self, chat_id: int) -> bool:
        return self._get(chat_id).awaiting_edit_reply

    def clear_awaiting_edit(self, chat_id: int) -> None:
        self._get(chat_id).awaiting_edit_reply = False

    def set_pending_plan(
        self,
        chat_id: int,
        steps: list,
        timeout_task: asyncio.Task,
    ) -> None:
        entry = self._get(chat_id)
        entry.pending_plan = steps
        entry.plan_task = timeout_task

    def get_pending_plan(self, chat_id: int) -> tuple[list | None, "asyncio.Task | None"]:
        entry = self._get(chat_id)
        return entry.pending_plan, entry.plan_task

    def cancel_plan_task(self, chat_id: int) -> None:
        entry = self._get(chat_id)
        if entry.plan_task:
            entry.plan_task.cancel()
            entry.plan_task = None
        entry.pending_plan = None

    def set_awaiting_goal_redirect(self, chat_id: int, gate_id: str) -> None:
        self._get(chat_id).awaiting_goal_redirect = gate_id

    def get_awaiting_goal_redirect(self, chat_id: int) -> str | None:
        return self._get(chat_id).awaiting_goal_redirect

    def clear_awaiting_goal_redirect(self, chat_id: int) -> None:
        self._get(chat_id).awaiting_goal_redirect = None

    def clear_all(self, chat_id: int) -> None:
        self.cancel_confirm_task(chat_id)
        self.cancel_plan_task(chat_id)
        entry = self._get(chat_id)
        entry.active = False
        entry.awaiting_edit_reply = False
        entry.awaiting_goal_redirect = None
