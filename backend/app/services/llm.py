from __future__ import annotations

import json
import re
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
        json_system = (
            f"{system}\n"
            "必须只返回一个合法 JSON 对象，不要包含 Markdown 代码块、解释或额外文本。"
        )
        try:
            text = await self._chat(
                json_system,
                user,
                response_format={"type": "json_object"},
            )
            return self._loads_json(text)
        except Exception:
            try:
                text = await self._chat(json_system, user)
                return self._loads_json(text)
            except Exception:
                return fallback

    async def complete_text(self, system: str, user: str, fallback: str) -> str:
        if not self.client or not self.settings.openai_model:
            return fallback
        try:
            return await self._chat(system, user) or fallback
        except Exception:
            return fallback

    async def _chat(
        self,
        system: str,
        user: str,
        response_format: dict[str, str] | None = None,
    ) -> str:
        if not self.client or not self.settings.openai_model:
            return ""
        kwargs: dict[str, Any] = {
            "model": self.settings.openai_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
            "timeout": self.settings.llm_timeout_seconds,
        }
        if response_format:
            kwargs["response_format"] = response_format
        response = await self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""

    def _loads_json(self, text: str) -> Any:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.S)
            if not match:
                raise
            return json.loads(match.group(0))
