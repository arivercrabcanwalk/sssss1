from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI

from app.config import get_settings


class LLMClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.available = bool(self.settings.openai_api_key and self.settings.openai_model)
        self.client: AsyncOpenAI | None = None
        if self.available:
            kwargs: dict[str, Any] = {"api_key": self.settings.openai_api_key}
            if self.settings.openai_base_url:
                kwargs["base_url"] = self.settings.openai_base_url
            self.client = AsyncOpenAI(**kwargs)

    async def complete_json(self, system: str, user: str, fallback: Any) -> Any:
        if not self.client or not self.settings.openai_model:
            return fallback
        try:
            response = await self.client.chat.completions.create(
                model=self.settings.openai_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.2,
                response_format={"type": "json_object"},
                timeout=self.settings.llm_timeout_seconds,
            )
            text = response.choices[0].message.content or "{}"
            return json.loads(text)
        except Exception:
            return fallback

    async def complete_text(self, system: str, user: str, fallback: str) -> str:
        if not self.client or not self.settings.openai_model:
            return fallback
        try:
            response = await self.client.chat.completions.create(
                model=self.settings.openai_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.2,
                timeout=self.settings.llm_timeout_seconds,
            )
            return response.choices[0].message.content or fallback
        except Exception:
            return fallback
