from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ze_agents.logging import get_logger
from ze_browser import BrowserClient
from ze_ingestion import ContentClassifier, IngestionPipeline, IngestionStore, MemorySink
from ze_ingestion.extractors.llm import LLMExtractor
from ze_ingestion.fetchers.browser import BrowserFetcher
from ze_ingestion.fetchers.web import WebFetcher
from ze_ingestion.processors.audio import AudioProcessor
from ze_ingestion.processors.html import HtmlProcessor
from ze_ingestion.processors.image import ImageProcessor
from ze_ingestion.processors.pdf import PdfProcessor
from ze_ingestion.processors.text import TextProcessor

log = get_logger(__name__)

_AGENT_MODULE_PATH = "ze_ingestion.agent"


@dataclass
class IngestionStack:
    pipeline: IngestionPipeline


def agent_module_paths() -> list[str]:
    return [_AGENT_MODULE_PATH]


def import_agent_modules() -> None:
    import importlib

    importlib.import_module(_AGENT_MODULE_PATH)


def build_ingestion_stack(
    shared: Any,
    settings: Any,
    plugins: list,
    *,
    browser_client: BrowserClient,
) -> IngestionStack:
    ingestion_store = IngestionStore(pool=shared.pool)
    memory_sink = MemorySink(memory_store=shared.memory_store)
    classifier = ContentClassifier()

    plugin_fetchers = [f for plugin in plugins for f in plugin.ingestion_fetchers()]
    plugin_extractors = [e for plugin in plugins for e in plugin.ingestion_extractors()]

    yt_fetcher = None
    try:
        from ze_yt import YtDlpFetcher

        yt_fetcher = YtDlpFetcher()
        log.info("ze_yt_fetcher_registered")
    except ImportError:
        pass

    ingestion_fetchers_list: list = []
    if yt_fetcher is not None:
        ingestion_fetchers_list.append(yt_fetcher)
    ingestion_fetchers_list.extend(plugin_fetchers)
    ingestion_fetchers_list.append(BrowserFetcher(browser_client=browser_client))
    ingestion_fetchers_list.append(WebFetcher())

    extraction_model = settings.config.get("models", {}).get(
        "ingestion_extraction",
        "anthropic/claude-haiku-4-5",
    )
    pipeline = IngestionPipeline(
        classifier=classifier,
        fetchers=ingestion_fetchers_list,
        processors=[
            HtmlProcessor(),
            PdfProcessor(),
            AudioProcessor(llm_client=shared.openrouter_client),
            ImageProcessor(llm_client=shared.openrouter_client),
            TextProcessor(),
        ],
        extractors=[
            LLMExtractor(llm_client=shared.openrouter_client, model=extraction_model),
        ]
        + plugin_extractors,
        store=ingestion_store,
        memory_sink=memory_sink,
    )

    from ze_ingestion.agent import _set_pipeline

    _set_pipeline(pipeline)
    log.info("ingestion_pipeline_ready")
    return IngestionStack(pipeline=pipeline)
