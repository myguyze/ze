from aiogram import Bot
from aiogram.types import CallbackQuery, Message

from ze.logging import bind_context, unbind_context
from ze.telegram.context import BotContext
from ze.telegram.dispatch.callbacks import dispatch_callback
from ze.telegram.dispatch.media import dispatch_photo, dispatch_voice
from ze.telegram.dispatch.messages import dispatch_message
from ze.telegram.interface import TelegramAppInterface
from ze.telegram.session import ActiveSessionStore
from ze_core.progress import ProgressTranslations
from ze.telegram.core.graph import invoke as invoke_graph


class ZeBot:
    def __init__(
        self,
        bot: Bot,
        graph,
        workflow_graph,
        store: ActiveSessionStore,
        router,
        capability_gate,
        memory_store,
        persona_store,
        person_store,
        workflow_store,
        workflow_planner,
        openrouter_client,
        embedder,
        settings,
        translations: ProgressTranslations | None = None,
        pool=None,
        contact_channel_store=None,
        goal_store=None,
        goal_executor=None,
        goal_planner=None,
        goal_suggestion_store=None,
        interface: TelegramAppInterface | None = None,
    ) -> None:
        self._ctx = BotContext(
            bot=bot,
            store=store,
            container=None,
            graph=graph,
            workflow_graph=workflow_graph,
            router=router,
            capability_gate=capability_gate,
            memory_store=memory_store,
            persona_store=persona_store,
            person_store=person_store,
            workflow_store=workflow_store,
            workflow_planner=workflow_planner,
            openrouter_client=openrouter_client,
            embedder=embedder,
            settings=settings,
            translations=translations,
            pool=pool,
            contact_channel_store=contact_channel_store,
            goal_store=goal_store,
            goal_executor=goal_executor,
            goal_planner=goal_planner,
            goal_suggestion_store=goal_suggestion_store,
            interface=interface,
        )

    def bind_container(self, container) -> None:
        """Attach the app container after construction (avoids a circular import)."""
        self._ctx.container = container

    async def handle_message(self, message: Message) -> None:
        bind_context(str(message.chat.id))
        try:
            await dispatch_message(self._ctx, message)
        finally:
            unbind_context()

    async def handle_voice(self, message: Message) -> None:
        bind_context(str(message.chat.id))
        try:
            await dispatch_voice(self._ctx, message)
        finally:
            unbind_context()

    async def handle_photo(self, message: Message) -> None:
        bind_context(str(message.chat.id))
        try:
            await dispatch_photo(self._ctx, message)
        finally:
            unbind_context()

    async def handle_callback(self, query: CallbackQuery) -> None:
        bind_context(str(query.message.chat.id))
        try:
            await dispatch_callback(self._ctx, query)
        finally:
            unbind_context()

    async def invoke(self, prompt: str, session_id: str) -> dict:
        """Invoke the graph directly for eval/testing. Returns raw final state."""
        return await invoke_graph(self._ctx, prompt, session_id)
