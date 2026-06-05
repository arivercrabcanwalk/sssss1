from __future__ import annotations

from app.models import AgentAction, ExecutionRun, TestScenario, VerificationResult
from app.services.llm import LLMClient


class RunVerifier:
    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm or LLMClient()

    async def verify(self, run: ExecutionRun, scenario: TestScenario) -> VerificationResult:
        failed = [action for action in run.actions if action.status == "failed"]
        evidence = [obs for obs in (action.observation for action in run.actions) if obs]
        error_types: list[str] = []
        if failed:
            error_types.append("execution_exception")
        if any("overlap" in item.lower() or "overflow" in item.lower() for item in evidence):
            error_types.append("layout_issue")
        rule_passed = not failed and bool(run.actions)
        fallback = {
            "passed": rule_passed,
            "score": 0.85 if rule_passed else 0.25,
            "failure_reason": None if rule_passed else failed[0].error or failed[0].observation,
            "evidence": evidence[-8:],
            "error_types": error_types,
        }
        data = await self.llm.complete_json(
            system=(
                "你是 Web 测试验证器。根据测试场景、操作轨迹和页面观察，判断是否成功。"
                "输出 JSON: {passed:boolean, score:number, failure_reason:string|null, evidence:string[], error_types:string[]}"
            ),
            user=(
                f"场景: {scenario.model_dump(mode='json')}\n"
                f"轨迹: {[action.model_dump(mode='json') for action in run.actions]}\n"
                f"规则兜底判定: {fallback}"
            ),
            fallback=fallback,
        )
        try:
            return VerificationResult.model_validate(data)
        except Exception:
            return VerificationResult.model_validate(fallback)
