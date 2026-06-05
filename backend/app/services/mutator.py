from __future__ import annotations

from copy import deepcopy

from app.models import MutationRequest, TestExpectation, TestScenario, TestStep
from app.rag.chunking import stable_id


class ScenarioMutator:
    def mutate(self, scenario: TestScenario, request: MutationRequest) -> list[TestScenario]:
        mutations: list[TestScenario] = []
        for mutation_type in request.mutation_types:
            if mutation_type == "boundary_input":
                mutations.append(self._boundary_input(scenario))
            elif mutation_type == "missing_required":
                mutations.append(self._missing_required(scenario))
            elif mutation_type == "wrong_order":
                mutations.append(self._wrong_order(scenario))
            elif mutation_type == "mobile_layout":
                mutations.append(self._mobile_layout(scenario))
            elif mutation_type == "duplicate_submit":
                mutations.append(self._duplicate_submit(scenario))
        return mutations

    def _clone(self, scenario: TestScenario, mutation_type: str, title_suffix: str) -> TestScenario:
        clone = deepcopy(scenario)
        clone.id = stable_id("scenario", f"{scenario.id}:{mutation_type}")
        clone.title = f"{scenario.title} - {title_suffix}"
        clone.mutated_from = scenario.id
        clone.mutation_type = mutation_type
        clone.tags = sorted(set([*clone.tags, "mutation", mutation_type]))
        return clone

    def _boundary_input(self, scenario: TestScenario) -> TestScenario:
        clone = self._clone(scenario, "boundary_input", "边界输入变异")
        for step in clone.steps:
            if step.value:
                step.value = step.value + " " + "X" * 240
                step.expectation = "系统应正确处理超长输入，不应崩溃或产生布局溢出"
                break
        return clone

    def _missing_required(self, scenario: TestScenario) -> TestScenario:
        clone = self._clone(scenario, "missing_required", "缺失必填项变异")
        for step in clone.steps:
            if step.value:
                step.value = ""
                step.expectation = "系统应提示必填校验或阻止提交"
                break
        return clone

    def _wrong_order(self, scenario: TestScenario) -> TestScenario:
        clone = self._clone(scenario, "wrong_order", "错误顺序变异")
        if len(clone.steps) >= 2:
            clone.steps[0], clone.steps[1] = clone.steps[1], clone.steps[0]
            for index, step in enumerate(clone.steps, 1):
                step.index = index
        return clone

    def _mobile_layout(self, scenario: TestScenario) -> TestScenario:
        clone = self._clone(scenario, "mobile_layout", "移动端布局变异")
        clone.tags = sorted(set([*clone.tags, "mobile"]))
        clone.expectations.append(
            TestExpectation(
                description="移动视口下关键控件不应互相遮挡",
                observable="页面可见区域内没有明显重叠、溢出或不可点击元素",
                severity="major",
            )
        )
        return clone

    def _duplicate_submit(self, scenario: TestScenario) -> TestScenario:
        clone = self._clone(scenario, "duplicate_submit", "重复提交变异")
        submit_index = None
        for i, step in enumerate(clone.steps):
            text = f"{step.action} {step.target or ''}".lower()
            if "submit" in text or "保存" in text or "提交" in text:
                submit_index = i
        if submit_index is not None:
            duplicate = deepcopy(clone.steps[submit_index])
            duplicate.index = clone.steps[submit_index].index + 1
            duplicate.expectation = "重复提交不应产生重复数据或执行异常"
            clone.steps.insert(submit_index + 1, duplicate)
        else:
            clone.steps.append(
                TestStep(
                    index=len(clone.steps) + 1,
                    action="重复执行主要提交操作",
                    expectation="系统不应产生重复数据或异常",
                )
            )
        for index, step in enumerate(clone.steps, 1):
            step.index = index
        return clone
