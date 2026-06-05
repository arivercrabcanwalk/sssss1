from __future__ import annotations

from app.models import AgentAction, TestScenario


class TestPlanner:
    def plan(self, scenario: TestScenario, target_url: str) -> list[AgentAction]:
        actions = [
            AgentAction(
                index=1,
                thought="打开目标 4ga Boards 应用，建立初始页面上下文",
                tool="goto",
                value=target_url,
            )
        ]
        for step in scenario.steps:
            action_text = step.action.lower()
            selector = step.target
            tool = "inspect"
            value = step.value
            if selector and any(word in action_text for word in ["点击", "click", "打开", "进入", "提交", "保存"]):
                tool = "click"
            elif selector and any(word in action_text for word in ["填写", "输入", "搜索", "fill", "type"]):
                tool = "fill"
            elif any(word in action_text for word in ["等待", "wait"]):
                tool = "wait"
            actions.append(
                AgentAction(
                    index=len(actions) + 1,
                    thought=f"执行场景步骤 {step.index}: {step.action}",
                    tool=tool,
                    selector=selector,
                    value=value,
                )
            )
            if step.expectation:
                actions.append(
                    AgentAction(
                        index=len(actions) + 1,
                        thought=f"检查步骤 {step.index} 预期: {step.expectation}",
                        tool="assert_text",
                        value=step.expectation,
                    )
                )
        actions.append(
            AgentAction(
                index=len(actions) + 1,
                thought="保存最终截图用于轨迹验证和报告",
                tool="screenshot",
            )
        )
        return actions
