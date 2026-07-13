from __future__ import annotations

from typing import Any

from ze_components.atoms import info, muted, subheading, text
from ze_components.molecules import card, col
from ze_components.serialize import serialize_tree


def build_news_settings(news_cfg: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not news_cfg or not news_cfg.get("sources"):
        children: list[object] = [
            text("News is not configured."),
            muted(
                "Add RSS sources under news.sources in config.yaml to enable fetching."
            ),
        ]
        return serialize_tree([col(children)])

    sources = news_cfg.get("sources", [])
    schedule = str(news_cfg.get("fetch_schedule", "*/30 * * * *"))
    credibility_on = bool(news_cfg.get("credibility", {}).get("enabled", False))
    personalization_on = bool(news_cfg.get("personalization", {}).get("enabled", False))

    source_rows: list[object] = []
    for source in sources:
        tags = ", ".join(source.get("tags", [])) or "untagged"
        source_rows.append(
            card(
                [
                    subheading(str(source.get("key", "source"))),
                    muted(str(source.get("url", ""))),
                    info(tags),
                ],
                gap="none",
            )
        )

    summary = col(
        [
            text(f"{len(sources)} RSS sources"),
            muted(f"Fetch schedule: {schedule}"),
            info(
                "Credibility scoring on"
                if credibility_on
                else "Credibility scoring off"
            ),
            info("Personalization on" if personalization_on else "Personalization off"),
        ],
        gap="none",
    )

    return serialize_tree([col([summary, *source_rows])])
