from __future__ import annotations

import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from app.config import get_settings
from app.models import AppState, DocPage, ExecutionRun, FeaturePoint, KnowledgeChunk, TestScenario

T = TypeVar("T", bound=BaseModel)


class JsonStore:
    def __init__(self) -> None:
        self.settings = get_settings()
        for directory in [
            self.settings.raw_dir,
            self.settings.index_dir,
            self.settings.runs_dir,
            self.settings.reports_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)
        self.state_path = self.settings.data_dir / "state.json"

    def load_state(self) -> AppState:
        if not self.state_path.exists():
            return AppState()
        data = json.loads(self.state_path.read_text(encoding="utf-8"))
        return AppState(
            docs=[DocPage.model_validate(item) for item in data.get("docs", [])],
            chunks=[KnowledgeChunk.model_validate(item) for item in data.get("chunks", [])],
            features=[FeaturePoint.model_validate(item) for item in data.get("features", [])],
            scenarios=[TestScenario.model_validate(item) for item in data.get("scenarios", [])],
            runs={
                key: ExecutionRun.model_validate(value)
                for key, value in data.get("runs", {}).items()
            },
            extra=data.get("extra", {}),
        )

    def save_state(self, state: AppState) -> None:
        self.state_path.write_text(
            state.model_dump_json(indent=2, exclude_none=True),
            encoding="utf-8",
        )

    def write_json(self, path: Path, data: BaseModel | list[BaseModel] | dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, list):
            payload = [item.model_dump(mode="json", exclude_none=True) for item in data]
        elif isinstance(data, BaseModel):
            payload = data.model_dump(mode="json", exclude_none=True)
        else:
            payload = data
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def read_json(self, path: Path) -> dict | list:
        return json.loads(path.read_text(encoding="utf-8"))
