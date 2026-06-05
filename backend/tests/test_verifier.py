import pytest

from app.agent.verifier import RunVerifier
from app.models import (
    ActionStatus,
    AgentAction,
    DocRef,
    ExecutionRun,
    TestExpectation,
    TestScenario,
    TestStep,
)


@pytest.mark.asyncio
async def test_verifier_classifies_failed_action() -> None:
    scenario = TestScenario(
        id="s1",
        feature_id="f1",
        title="Card creation",
        steps=[TestStep(index=1, action="click add card")],
        expectations=[TestExpectation(description="card is visible", observable="card")],
        oracle="card visible",
        evidence_refs=[
            DocRef(id="d1", title="Cards", url="https://docs.4gaboards.com/docs/card/", snippet="Cards")
        ],
    )
    run = ExecutionRun(id="r1", scenario_id="s1", target_url="http://127.0.0.1:3000")
    run.actions.append(
        AgentAction(
            index=1,
            thought="click",
            tool="click",
            status=ActionStatus.failed,
            error="selector not found",
        )
    )

    verdict = await RunVerifier().verify(run, scenario)

    assert not verdict.passed
    assert "execution_exception" in verdict.error_types
