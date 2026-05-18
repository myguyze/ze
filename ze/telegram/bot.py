import asyncio

from aiogram import Bot
from aiogram.types import CallbackQuery, ForceReply, Message

from ze.logging import bind_context, get_logger, unbind_context
from ze.telegram.keyboards import confirmation_keyboard
from ze.telegram.session import ActiveSessionStore

log = get_logger(__name__)

_MAX_MESSAGE_LEN = 4096


class ZeBot:
    def __init__(
        self,
        bot: Bot,
        graph,
        store: ActiveSessionStore,
        router,
        capability_gate,
        memory_store,
        openrouter_client,
        embedder,
        settings,
    ) -> None:
        self._bot = bot
        self._graph = graph
        self._store = store
        self._router = router
        self._capability_gate = capability_gate
        self._memory_store = memory_store
        self._openrouter_client = openrouter_client
        self._embedder = embedder
        self._settings = settings

    # ── Public handlers ───────────────────────────────────────────────────────

    async def handle_message(self, message: Message) -> None:
        chat_id = message.chat.id
        text = message.text or ""
        bind_context(chat_id=chat_id)

        try:
            if self._store.is_awaiting_edit(chat_id):
                await self._handle_edit_reply(chat_id, text)
                return

            if self._store.is_active(chat_id):
                await self._bot.send_message(chat_id, "A task is already in progress.")
                return

            self._store.mark_active(chat_id)
            log.info("message_received", chat_id=chat_id)
            await self._run_graph(chat_id, text)
        finally:
            unbind_context()

    async def handle_callback(self, query: CallbackQuery) -> None:
        chat_id = query.message.chat.id
        data = query.data or ""
        bind_context(chat_id=chat_id)

        try:
            if not data.startswith("confirm:"):
                await query.answer()
                return

            decision = data.split(":", 1)[1]
            await query.answer()

            # Remove keyboard from the confirmation message to prevent re-taps
            await query.message.edit_reply_markup(reply_markup=None)

            if decision == "edit":
                self._store.set_awaiting_edit(chat_id)
                await self._bot.send_message(
                    chat_id,
                    "Please reply with your edited version:",
                    reply_markup=ForceReply(selective=True),
                )
                return

            await self._resume_graph(chat_id, decision)
        finally:
            unbind_context()

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _handle_edit_reply(self, chat_id: int, text: str) -> None:
        self._store.clear_awaiting_edit(chat_id)
        self._store.cancel_confirm_task(chat_id)
        log.info("edit_reply_received", chat_id=chat_id)
        await self._resume_graph(chat_id, "edit", edit_content=text)

    async def _run_graph(self, chat_id: int, prompt: str) -> None:
        config = self._make_config(chat_id)
        state = self._make_initial_state(prompt, chat_id)

        typing_task = asyncio.create_task(self._keep_typing(chat_id))
        try:
            final_state = await self._graph.ainvoke(state, config)
        except Exception as exc:
            log.exception("graph_error", chat_id=chat_id, error=str(exc))
            self._store.clear_all(chat_id)
            await self._bot.send_message(chat_id, "Something went wrong. Try again.")
            return
        finally:
            typing_task.cancel()

        graph_state = await self._graph.aget_state(config)
        if graph_state.next:
            # Graph interrupted — needs confirmation
            result = final_state.get("agent_result")
            envelope = final_state.get("envelope")
            draft = result.response if result else ""
            agent = envelope.primary_agent if envelope else ""
            action = (
                envelope.subtasks[0].intent
                if envelope and envelope.subtasks
                else ""
            )
            await self._send_confirmation(chat_id, draft, agent, action, config)
        else:
            response = _extract_response(final_state)
            self._store.clear_active(chat_id)
            await self._send_response(chat_id, response)
            log.info("graph_complete", chat_id=chat_id)

    async def _resume_graph(
        self,
        chat_id: int,
        decision: str,
        edit_content: str | None = None,
    ) -> None:
        self._store.cancel_confirm_task(chat_id)
        config = self._store.get_pending_config(chat_id)
        if config is None:
            await self._bot.send_message(chat_id, "No pending confirmation.")
            return

        self._store.mark_active(chat_id)

        if decision == "no":
            self._store.clear_all(chat_id)
            await self._bot.send_message(chat_id, "Action cancelled.")
            return

        if decision == "edit" and edit_content is not None:
            await self._graph.aupdate_state(
                config,
                {"agent_result": None, "prompt": edit_content},
            )

        typing_task = asyncio.create_task(self._keep_typing(chat_id))
        try:
            final_state = await self._graph.ainvoke(None, config)
        except Exception as exc:
            log.exception("resume_error", chat_id=chat_id, error=str(exc))
            self._store.clear_all(chat_id)
            await self._bot.send_message(chat_id, "Something went wrong. Try again.")
            return
        finally:
            typing_task.cancel()

        self._store.clear_all(chat_id)
        response = _extract_response(final_state)
        await self._send_response(chat_id, response)
        log.info("resume_complete", chat_id=chat_id)

    async def _send_confirmation(
        self,
        chat_id: int,
        draft: str,
        agent: str,
        action: str,
        config: dict,
    ) -> None:
        text = (
            f"⚠️ *Confirmation required*\n\n"
            f"*Agent:* {agent}\n"
            f"*Action:* {action}\n"
            f"*Draft:*\n```\n{draft}\n```"
        )
        await self._bot.send_message(
            chat_id,
            text,
            parse_mode="Markdown",
            reply_markup=confirmation_keyboard(),
        )

        timeout_task = asyncio.create_task(
            self._confirmation_timeout(chat_id, config)
        )
        self._store.clear_active(chat_id)
        self._store.set_pending_confirmation(chat_id, config, timeout_task)
        log.info("awaiting_confirmation", chat_id=chat_id, agent=agent)

    async def _confirmation_timeout(self, chat_id: int, config: dict) -> None:
        try:
            await asyncio.sleep(self._settings.confirm_timeout_seconds)
            await self._graph.aupdate_state(config, {"error": "confirmation_expired"})
            self._store.clear_all(chat_id)
            await self._bot.send_message(
                chat_id,
                "⏱ Confirmation expired. The action was cancelled.",
            )
            log.info("confirmation_expired", chat_id=chat_id)
        except asyncio.CancelledError:
            pass

    async def _keep_typing(self, chat_id: int) -> None:
        try:
            while True:
                await self._bot.send_chat_action(chat_id, "typing")
                await asyncio.sleep(4)
        except asyncio.CancelledError:
            pass

    async def _send_response(self, chat_id: int, text: str) -> None:
        if not text:
            return
        for chunk in _split(text):
            await self._bot.send_message(chat_id, chunk)

    def _make_config(self, chat_id: int) -> dict:
        return {
            "configurable": {
                "thread_id": str(chat_id),
                "router": self._router,
                "capability_gate": self._capability_gate,
                "memory_store": self._memory_store,
                "openrouter_client": self._openrouter_client,
                "embedder": self._embedder,
                "settings": self._settings,
            }
        }

    @staticmethod
    def _make_initial_state(prompt: str, chat_id: int) -> dict:
        return {
            "prompt": prompt,
            "session_id": str(chat_id),
            "session_overrides": {},
            "envelope": None,
            "memory_context": None,
            "agent_context": None,
            "gate_decision": None,
            "agent_result": None,
            "subtask_results": [],
            "pending_confirmation": False,
            "final_response": None,
            "error": None,
        }


def _extract_response(state: dict) -> str:
    """Return the best available response text from a completed graph state."""
    if state.get("final_response"):
        return state["final_response"]
    result = state.get("agent_result")
    if result and result.response:
        return result.response
    return ""


def _split(text: str, limit: int = _MAX_MESSAGE_LEN) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        cut = text.rfind("\n", 0, limit)
        if cut == -1:
            cut = limit
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    return chunks
