import pytest

from app.models import GenerateRequest, MutationRequest
from app.models import DocRef, FeaturePoint
from app.rag.chunking import chunk_pages
from app.rag.retriever import HybridRetriever
from app.services.fallback_docs import fallback_docs
from app.services.mutator import ScenarioMutator
from app.services.scenario_generator import ScenarioGenerator


@pytest.mark.asyncio
async def test_generate_scenarios_with_evidence() -> None:
    chunks = chunk_pages(fallback_docs())
    retriever = HybridRetriever()
    retriever.build(chunks)
    generator = ScenarioGenerator(retriever)

    features, scenarios = await generator.generate(
        chunks,
        GenerateRequest(max_features=8, scenarios_per_feature=2, use_llm=False),
    )

    assert len(features) >= 4
    assert len(scenarios) >= len(features)
    assert all(feature.doc_refs for feature in features)
    assert all(scenario.evidence_refs for scenario in scenarios)
    assert all(scenario.steps for scenario in scenarios)


def test_mutations_keep_traceability() -> None:
    chunks = chunk_pages(fallback_docs())
    retriever = HybridRetriever()
    retriever.build(chunks)

    async def generate_first():
        generator = ScenarioGenerator(retriever)
        _, scenarios = await generator.generate(
            chunks,
            GenerateRequest(max_features=3, scenarios_per_feature=1, use_llm=False),
        )
        return scenarios[0]

    import asyncio

    scenario = asyncio.run(generate_first())
    mutations = ScenarioMutator().mutate(scenario, request=MutationRequest())

    assert mutations
    assert all(item.mutated_from == scenario.id for item in mutations)
    assert any(item.mutation_type == "mobile_layout" for item in mutations)


@pytest.mark.asyncio
async def test_llm_scenario_normalizes_loose_string_fields() -> None:
    class FakeLLM:
        async def complete_json(self, system: str, user: str, fallback: dict) -> dict:
            return {
                "scenarios": [
                    {
                        "feature_id": "feature_loose",
                        "title": "字符串字段兼容",
                        "difficulty": "simple",
                        "tags": "llm",
                        "steps": ["打开项目页面", {"action": "点击新建项目", "target": "button"}],
                        "expectations": ["页面显示新项目"],
                        "oracle": "根据轨迹验证页面状态",
                    }
                ]
            }

    feature = FeaturePoint(
        id="feature_loose",
        name="项目管理",
        description="项目管理功能",
        doc_refs=[
            DocRef(
                id="doc1",
                title="Projects",
                url="https://docs.4gaboards.com/docs/project/",
                snippet="Users can create projects.",
            )
        ],
    )
    generator = ScenarioGenerator(HybridRetriever(), llm=FakeLLM())

    scenarios = await generator._llm_refine_scenarios([feature], [], scenarios_per_feature=1)

    assert scenarios[0].steps[0].action == "打开项目页面"
    assert scenarios[0].expectations[0].description == "页面显示新项目"
    assert scenarios[0].tags == ["llm"]


@pytest.mark.asyncio
async def test_llm_english_scenario_falls_back_to_chinese_rules() -> None:
    class EnglishLLM:
        async def complete_json(self, system: str, user: str, fallback: dict) -> dict:
            return {
                "scenarios": [
                    {
                        "feature_id": "feature_project",
                        "title": "Create a new project with a valid name",
                        "difficulty": "medium",
                        "tags": ["smoke", "happy-path"],
                        "steps": [
                            {"action": "navigate", "expectation": "Project list page is loaded"},
                            {"action": "click", "expectation": "A project creation form is displayed"},
                            {"action": "type", "expectation": "Project name field contains Sprint Alpha"},
                        ],
                        "expectations": ["Project is created"],
                        "oracle": "Verify the project appears in the project list.",
                    }
                ]
            }

    feature = FeaturePoint(
        id="feature_project",
        name="项目管理",
        description="项目管理功能",
        doc_refs=[
            DocRef(
                id="doc1",
                title="Projects",
                url="https://docs.4gaboards.com/docs/project/",
                snippet="Users can create projects.",
            )
        ],
    )
    generator = ScenarioGenerator(HybridRetriever(), llm=EnglishLLM())
    fallback = generator._rule_scenarios([feature], scenarios_per_feature=1)

    scenarios = await generator._llm_refine_scenarios([feature], fallback, scenarios_per_feature=1)

    assert scenarios[0].title == "项目管理 - 基础创建流程"
    assert scenarios[0].steps[0].action == "打开应用首页并登录"
    assert "navigate" not in {step.action for step in scenarios[0].steps}


@pytest.mark.asyncio
async def test_llm_medium_only_scenarios_fall_back_to_difficulty_ladder() -> None:
    class MediumOnlyLLM:
        async def complete_json(self, system: str, user: str, fallback: dict) -> dict:
            return {
                "scenarios": [
                    {
                        "feature_id": "feature_project",
                        "title": "创建项目流程",
                        "difficulty": "medium",
                        "tags": ["项目"],
                        "steps": [{"action": "打开项目页面", "expectation": "项目列表显示"}],
                        "expectations": ["项目创建成功"],
                        "oracle": "验证项目是否出现",
                    },
                    {
                        "feature_id": "feature_project",
                        "title": "编辑项目流程",
                        "difficulty": "medium",
                        "tags": ["项目"],
                        "steps": [{"action": "打开项目设置", "expectation": "设置页显示"}],
                        "expectations": ["项目设置保存成功"],
                        "oracle": "验证设置是否保留",
                    },
                ]
            }

    feature = FeaturePoint(
        id="feature_project",
        name="项目管理",
        description="项目管理功能",
        doc_refs=[
            DocRef(
                id="doc1",
                title="Projects",
                url="https://docs.4gaboards.com/docs/project/",
                snippet="Users can create projects.",
            )
        ],
    )
    generator = ScenarioGenerator(HybridRetriever(), llm=MediumOnlyLLM())
    fallback = generator._rule_scenarios([feature], scenarios_per_feature=3)

    scenarios = await generator._llm_refine_scenarios([feature], fallback, scenarios_per_feature=3)

    assert [scenario.difficulty for scenario in scenarios] == ["simple", "medium", "hard"]
