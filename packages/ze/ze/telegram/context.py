from __future__ import annotations

from dataclasses import dataclass

from aiogram import Bot

from ze.telegram.interface import TelegramAppInterface
from ze.telegram.session import ActiveSessionStore
from ze_core.progress import ProgressTranslations


@dataclass
class BotContext:
    bot: Bot
    store: ActiveSessionStore
    container: object | None
    graph: object
    workflow_graph: object
    router: object
    capability_gate: object
    memory_store: object
    persona_store: object
    person_store: object
    workflow_store: object
    workflow_planner: object
    openrouter_client: object
    embedder: object
    settings: object
    translations: ProgressTranslations | None = None
    pool: object | None = None
    contact_channel_store: object | None = None
    goal_store: object | None = None
    goal_executor: object | None = None
    goal_planner: object | None = None
    goal_suggestion_store: object | None = None
    interface: TelegramAppInterface | None = None
