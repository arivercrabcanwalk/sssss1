from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime

from jinja2 import Template

from app.config import get_settings
from app.models import CoverageMetrics, ExecutionRun, FeaturePoint, TestScenario


REPORT_TEMPLATE = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>4ga Boards 智能测试报告</title>
  <style>
    body { font-family: "Segoe UI", Arial, sans-serif; margin: 32px; color: #172033; }
    h1, h2 { margin-bottom: 8px; }
    .grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
    .card { border: 1px solid #d9e2ec; border-radius: 8px; padding: 14px; }
    .pass { color: #067a46; font-weight: 700; }
    .fail { color: #b42318; font-weight: 700; }
    .muted { color: #667085; }
    .pill { display: inline-block; margin: 2px 6px 2px 0; padding: 3px 7px; border-radius: 5px; background: #eef3ff; color: #1f4eb8; font-size: 12px; font-weight: 700; }
    table { width: 100%; border-collapse: collapse; margin-top: 16px; }
    th, td { border-bottom: 1px solid #e6edf3; padding: 8px; text-align: left; vertical-align: top; }
    code { background: #f4f7fb; padding: 2px 4px; border-radius: 4px; }
  </style>
</head>
<body>
  <h1>4ga Boards 智能测试报告</h1>
  <p>生成时间：{{ generated_at }}</p>
  <div class="grid">
    <div class="card"><strong>功能点</strong><br>{{ coverage.feature_count }}</div>
    <div class="card"><strong>场景数</strong><br>{{ coverage.scenario_count }}</div>
    <div class="card"><strong>P0 功能</strong><br>{{ coverage.p0_count }}</div>
    <div class="card"><strong>中高难场景</strong><br>{{ coverage.medium_or_hard_count }}</div>
  </div>
  <h2>课程要求映射</h2>
  <table>
    <tbody>
      <tr><th>RAG 场景生成</th><td>功能点和场景均保留用户手册证据引用，降低模型幻觉风险。</td></tr>
      <tr><th>智能体执行</th><td>每次执行包含规划、上下文记忆、浏览器动作、轨迹记录与验证结论。</td></tr>
      <tr><th>难度分层</th><td>{% for key, value in difficulty_counts.items() %}<span class="pill">{{ difficulty_labels.get(key, key) }} {{ value }}</span>{% endfor %}</td></tr>
      <tr><th>变异测试</th><td>{% for key, value in mutation_counts.items() %}<span class="pill">{{ mutation_labels.get(key, key) }} {{ value }}</span>{% endfor %}</td></tr>
      <tr><th>错误识别</th><td>执行异常、布局问题、语义错误、测试预言不匹配会进入验证结果和失败类型统计。</td></tr>
    </tbody>
  </table>
  <h2>功能点覆盖</h2>
  <table>
    <thead><tr><th>功能点</th><th>优先级</th><th>证据</th><th>前置条件</th></tr></thead>
    <tbody>
      {% for feature in feature_rows %}
      <tr>
        <td><strong>{{ feature.name }}</strong><br><span class="muted">{{ feature.description }}</span></td>
        <td>{{ feature.priority }}</td>
        <td>{{ feature.refs }}</td>
        <td>{{ feature.preconditions }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  <h2>场景抽样</h2>
  <table>
    <thead><tr><th>场景</th><th>难度</th><th>类型</th><th>步骤数</th><th>测试预言</th></tr></thead>
    <tbody>
      {% for scenario in scenario_rows %}
      <tr>
        <td>{{ scenario.title }}</td>
        <td>{{ difficulty_labels.get(scenario.difficulty, scenario.difficulty) }}</td>
        <td>{{ scenario.kind }}</td>
        <td>{{ scenario.step_count }}</td>
        <td>{{ scenario.oracle }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  <h2>执行概览</h2>
  <table>
    <thead><tr><th>Run</th><th>Scenario</th><th>Status</th><th>Score</th><th>Failure</th><th>Duration</th></tr></thead>
    <tbody>
      {% for run in runs %}
      <tr>
        <td><code>{{ run.id }}</code></td>
        <td>{{ run.scenario_id }}</td>
        <td class="{{ 'pass' if run.status == 'passed' else 'fail' }}">{{ run.status }}</td>
        <td>{{ run.score }}</td>
        <td>{{ run.failure_reason or '' }}</td>
        <td>{{ run.duration_seconds }}s</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  <h2>失败类型</h2>
  <p>{{ error_counts or "暂无失败类型" }}</p>
</body>
</html>
"""


class Reporter:
    def __init__(self) -> None:
        self.settings = get_settings()

    def coverage(self, features: list[FeaturePoint], scenarios: list[TestScenario]) -> CoverageMetrics:
        doc_ref_count = len({ref.id for feature in features for ref in feature.doc_refs})
        return CoverageMetrics(
            feature_count=len(features),
            scenario_count=len(scenarios),
            doc_ref_count=doc_ref_count,
            p0_count=sum(1 for feature in features if feature.priority == "P0"),
            medium_or_hard_count=sum(1 for scenario in scenarios if scenario.difficulty in {"medium", "hard"}),
        )

    def write_report(
        self,
        report_id: str,
        features: list[FeaturePoint],
        scenarios: list[TestScenario],
        runs: list[ExecutionRun],
    ) -> dict[str, str]:
        coverage = self.coverage(features, scenarios)
        report_runs = [self._run_view(run) for run in runs]
        difficulty_counter = Counter(scenario.difficulty for scenario in scenarios)
        mutation_counter = Counter(scenario.mutation_type for scenario in scenarios if scenario.mutation_type)
        error_counter = Counter(
            error
            for run in runs
            if run.verdict
            for error in run.verdict.error_types
        )
        mutation_labels = {
            "boundary_input": "边界输入",
            "missing_required": "缺失必填",
            "wrong_order": "错误顺序",
            "mobile_layout": "移动布局",
            "duplicate_submit": "重复提交",
        }
        difficulty_labels = {"simple": "简单", "medium": "中等", "hard": "困难"}
        feature_rows = [
            {
                "name": feature.name,
                "description": feature.description,
                "priority": feature.priority,
                "refs": "、".join(ref.title for ref in feature.doc_refs[:3]),
                "preconditions": "；".join(feature.preconditions),
            }
            for feature in features
        ]
        scenario_rows = [
            {
                "title": scenario.title,
                "difficulty": scenario.difficulty,
                "kind": mutation_labels.get(scenario.mutation_type or "", "基础场景"),
                "step_count": len(scenario.steps),
                "oracle": scenario.oracle,
            }
            for scenario in scenarios[:24]
        ]
        html = Template(REPORT_TEMPLATE).render(
            generated_at=datetime.now(UTC).isoformat(),
            coverage=coverage,
            runs=report_runs,
            error_counts=dict(error_counter),
            difficulty_counts=dict(difficulty_counter),
            mutation_counts=dict(mutation_counter),
            difficulty_labels=difficulty_labels,
            mutation_labels=mutation_labels,
            feature_rows=feature_rows,
            scenario_rows=scenario_rows,
        )
        html_path = self.settings.reports_dir / f"{report_id}.html"
        json_path = self.settings.reports_dir / f"{report_id}.json"
        html_path.write_text(html, encoding="utf-8")
        json_path.write_text(
            json.dumps(
                {
                "coverage": coverage.model_dump(mode="json"),
                "difficulty_counts": dict(difficulty_counter),
                "mutation_counts": dict(mutation_counter),
                "runs": [run.model_dump(mode="json", exclude_none=True) for run in runs],
                "error_counts": dict(error_counter),
                "features": [feature.model_dump(mode="json") for feature in features],
                "scenarios": [scenario.model_dump(mode="json") for scenario in scenarios],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return {"html": str(html_path), "json": str(json_path)}

    def _run_view(self, run: ExecutionRun) -> dict:
        status = run.status.value if hasattr(run.status, "value") else str(run.status)
        return {
            "id": run.id,
            "scenario_id": run.scenario_id,
            "status": status,
            "score": run.verdict.score if run.verdict else "",
            "failure_reason": run.failure_reason or "",
            "duration_seconds": run.metrics.duration_seconds or "",
        }
