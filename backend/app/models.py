from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field, HttpUrl


class DocRef(BaseModel):
    id: str
    title: str
    url: str
    heading: str | None = None
    snippet: str


class DocPage(BaseModel):
    id: str
    title: str
    url: str
    content: str
    headings: list[str] = Field(default_factory=list)
    crawled_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class KnowledgeChunk(BaseModel):
    id: str
    page_id: str
    title: str
    url: str
    heading: str | None = None
    text: str
    keywords: list[str] = Field(default_factory=list)


class FeaturePoint(BaseModel):
    id: str
    name: str
    description: str
    doc_refs: list[DocRef]
    priority: Literal["P0", "P1", "P2"] = "P1"
    entities: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)


class TestStep(BaseModel):
    __test__: ClassVar[bool] = False

    index: int
    action: str
    target: str | None = None
    value: str | None = None
    expectation: str | None = None


class TestExpectation(BaseModel):
    __test__: ClassVar[bool] = False

    description: str
    observable: str
    severity: Literal["critical", "major", "minor"] = "major"


class TestScenario(BaseModel):
    __test__: ClassVar[bool] = False

    id: str
    feature_id: str
    title: str
    difficulty: Literal["simple", "medium", "hard"] = "simple"
    tags: list[str] = Field(default_factory=list)
    steps: list[TestStep]
    expectations: list[TestExpectation]
    oracle: str
    evidence_refs: list[DocRef]
    mutated_from: str | None = None
    mutation_type: str | None = None


class ActionStatus(str, Enum):
    pending = "pending"
    running = "running"
    passed = "passed"
    failed = "failed"
    skipped = "skipped"


class AgentAction(BaseModel):
    index: int
    thought: str
    tool: Literal[
        "goto",
        "click",
        "fill",
        "press",
        "wait",
        "screenshot",
        "assert_text",
        "inspect",
        "drag",
    ]
    selector: str | None = None
    value: str | None = None
    status: ActionStatus = ActionStatus.pending
    observation: str | None = None
    screenshot_path: str | None = None
    error: str | None = None


class VerificationResult(BaseModel):
    passed: bool
    score: float = Field(ge=0, le=1)
    failure_reason: str | None = None
    evidence: list[str] = Field(default_factory=list)
    error_types: list[
        Literal["execution_exception", "layout_issue", "semantic_error", "oracle_mismatch"]
    ] = Field(default_factory=list)


class ExecutionMetrics(BaseModel):
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    duration_seconds: float | None = None
    action_count: int = 0
    passed_actions: int = 0
    screenshot_count: int = 0
    viewport: str = "desktop"


class ExecutionRun(BaseModel):
    id: str
    scenario_id: str
    status: ActionStatus = ActionStatus.pending
    target_url: str
    plan: list[AgentAction] = Field(default_factory=list)
    actions: list[AgentAction] = Field(default_factory=list)
    trace: list[str] = Field(default_factory=list)
    verdict: VerificationResult | None = None
    failure_reason: str | None = None
    metrics: ExecutionMetrics = Field(default_factory=ExecutionMetrics)


class CoverageMetrics(BaseModel):
    feature_count: int
    scenario_count: int
    doc_ref_count: int
    p0_count: int
    medium_or_hard_count: int


class RunRequest(BaseModel):
    scenario_ids: list[str] | None = None
    target_url: HttpUrl | str | None = None
    headless: bool = True
    viewport: Literal["desktop", "mobile"] = "desktop"
    repeat: int = Field(default=1, ge=1, le=5)


class CrawlRequest(BaseModel):
    base_url: HttpUrl | str | None = None
    max_pages: int = Field(default=80, ge=1, le=400)
    refresh: bool = False


class GenerateRequest(BaseModel):
    max_features: int = Field(default=18, ge=1, le=80)
    scenarios_per_feature: int = Field(default=2, ge=1, le=5)
    use_llm: bool = True


class MutationRequest(BaseModel):
    mutation_types: list[
        Literal["boundary_input", "missing_required", "wrong_order", "mobile_layout", "duplicate_submit"]
    ] = Field(default_factory=lambda: ["boundary_input", "missing_required", "mobile_layout"])


class AppState(BaseModel):
    docs: list[DocPage] = Field(default_factory=list)
    chunks: list[KnowledgeChunk] = Field(default_factory=list)
    features: list[FeaturePoint] = Field(default_factory=list)
    scenarios: list[TestScenario] = Field(default_factory=list)
    runs: dict[str, ExecutionRun] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)
