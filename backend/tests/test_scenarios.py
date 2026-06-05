import pytest

from app.models import GenerateRequest, MutationRequest
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
