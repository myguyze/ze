from __future__ import annotations

import re

from ze_agents.client import LLMClient

_TITLE_SYSTEM = """Generate a short conversation title (maximum 8 words).
Describe what the user wanted. No quotes. No trailing punctuation. Return the title only."""

_MD_RE = re.compile(r"[#*_`~\[\]()]+")


def strip_markdown(text: str) -> str:
    return _MD_RE.sub("", text).strip()


class SessionTitleGenerator:
    def __init__(self, client: LLMClient, model: str) -> None:
        self._client = client
        self._model = model

    async def generate(self, *, user_text: str, assistant_text: str) -> str:
        user = strip_markdown(user_text[:500])
        assistant = strip_markdown(assistant_text[:500])
        response = await self._client.complete(
            model=self._model,
            messages=[
                {"role": "system", "content": _TITLE_SYSTEM},
                {"role": "user", "content": f"User: {user}\n\nAssistant: {assistant}"},
            ],
        )
        title = response.strip().strip('"').strip("'").rstrip(".")
        words = title.split()
        if len(words) > 8:
            title = " ".join(words[:8])
        return title
