from __future__ import annotations

import base64
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from jinja2 import Template

from app.config import get_settings
from app.models import CoverageMetrics, ExecutionRun, FeaturePoint, TestScenario


REPORT_TEMPLATE = r"""
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
    a.detail-link { color: #1f5eff; text-decoration: none; font-weight: 700; font-size: 13px; }
    a.detail-link:hover { text-decoration: underline; }

    /* per-run detail cards */
    .run-detail-card { border: 1px solid #d9e2ec; border-radius: 8px; padding: 18px; margin: 18px 0; }
    .run-detail-card h3 { margin: 0 0 4px; }
    .badge { display: inline-block; padding: 3px 10px; border-radius: 5px; font-weight: 700; font-size: 13px; margin-left: 8px; }
    .badge-pass { background: #e6f4ec; color: #067a46; }
    .badge-fail { background: #fde7e7; color: #b42318; }

    /* trace */
    .trace-block { background: #f8fafc; border-radius: 6px; padding: 10px 14px; margin: 10px 0; max-height: 180px; overflow-y: auto; font-size: 13px; }
    .trace-block span { display: block; padding: 2px 0; border-bottom: 1px solid #eef2f6; }

    /* action rows */
    .action-row { padding: 10px 12px; margin: 6px 0; background: #fafbfc; border-radius: 5px; border-left: 3px solid #d9e2ec; }
    .action-row.passed { border-left-color: #067a46; }
    .action-row.failed { border-left-color: #b42318; }
    .action-row .header { display: flex; gap: 10px; align-items: baseline; margin-bottom: 4px; }
    .action-row .header strong { min-width: 28px; }
    .action-row .header code { font-size: 12px; }

    /* screenshots */
    .screenshot-thumb { max-width: 400px; border: 1px solid #ddd; border-radius: 4px; margin: 6px 0; display: block; cursor: pointer; }
    .screenshot-thumb:hover { border-color: #1f5eff; }
    .lightbox { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,.85); z-index: 9999; place-items: center; }
    .lightbox:target { display: grid; }
    .lightbox img { max-width: 90vw; max-height: 90vh; }
    .close-lightbox { position: absolute; top: 20px; right: 30px; color: #fff; font-size: 36px; text-decoration: none; font-weight: 300; }
    .back-link { font-size: 13px; color: #1f5eff; text-decoration: none; }
    .back-link:hover { text-decoration: underline; }
    .error-type { display: inline-block; padding: 2px 7px; border-radius: 4px; background: #fde7e7; color: #b42318; margin: 2px 4px; font-size: 12px; }
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
    <thead><tr><th>Run</th><th>Scenario</th><th>执行者</th><th>Status</th><th>Score</th><th>Failure</th><th>Duration</th><th>详情</th></tr></thead>
    <tbody>
      {% for run in runs %}
      <tr>
        <td><code>{{ run.id }}</code></td>
        <td>{{ run.scenario_id }}</td>
        <td>{{ run.created_by }}</td>
        <td class="{{ 'pass' if run.status == 'passed' else 'fail' }}">{{ run.status }}</td>
        <td>{{ run.score }}</td>
        <td>{{ run.failure_reason or '' }}</td>
        <td>{{ run.duration_seconds }}s</td>
        <td><a class="detail-link" href="#detail-{{ run.id }}">查看详情</a></td>
      </tr>
      {% endfor %}
    </tbody>
  </table>

  <h2>执行详情</h2>
  {% for run in detailed_runs %}
  <div class="run-detail-card" id="detail-{{ run.id }}">
    <a class="back-link" href="#">↑ 返回概览</a>
    <h3>
      {{ run.scenario_title }}
      <span class="badge {{ 'badge-pass' if run.status == 'passed' else 'badge-fail' }}">{{ run.status }}</span>
    </h3>
    <p class="muted">{{ run.id }} · 执行者: {{ run.created_by }} · {{ run.viewport }} · {{ run.duration_seconds }}s · {{ run.action_count }} 步 / {{ run.passed_actions }} 通过</p>
    {% if run.verdict_error_types %}
    <p>{% for et in run.verdict_error_types %}<span class="error-type">{{ et }}</span>{% endfor %}</p>
    {% endif %}
    <h4>执行轨迹</h4>
    <div class="trace-block">
      {% for trace in run.traces %}<span>{{ trace }}</span>{% endfor %}
    </div>
    <h4>动作详情</h4>
    {% for action in run.actions %}
    <div class="action-row {{ action.status }}">
      <div class="header">
        <strong>#{{ action.index }}</strong>
        <code>{{ action.tool }}</code>
        <span>{{ action.thought }}</span>
      </div>
      {% if action.observation %}<p class="muted">{{ action.observation }}</p>{% endif %}
      {% if action.error %}<p class="fail">{{ action.error }}</p>{% endif %}
      {% if action.screenshot_base64 %}
      <a href="#lb-{{ run.id }}-{{ action.index }}"><img class="screenshot-thumb" src="data:image/png;base64,{{ action.screenshot_base64 }}" alt="screenshot step {{ action.index }}" /></a>
      <div class="lightbox" id="lb-{{ run.id }}-{{ action.index }}">
        <a href="#detail-{{ run.id }}" class="close-lightbox">&times;</a>
        <img src="data:image/png;base64,{{ action.screenshot_base64 }}" alt="screenshot" />
      </div>
      {% endif %}
    </div>
    {% endfor %}
  </div>
  {% endfor %}

  <h2>失败类型</h2>
  {% if error_counts %}
  <table>
    <thead><tr><th>错误类型</th><th>数量</th></tr></thead>
    <tbody>
      {% for type, count in error_counts.items() %}
      <tr><td>{{ type }}</td><td>{{ count }}</td></tr>
      {% endfor %}
    </tbody>
  </table>
  {% else %}
  <p>暂无失败类型</p>
  {% endif %}
</body>
</html>
"""


def _read_screenshot_base64(screenshot_path: str | None) -> str | None:
    """Read a screenshot file and return its base64-encoded data URI payload."""
    if not screenshot_path:
        return None
    try:
        data = Path(screenshot_path).read_bytes()
        return base64.b64encode(data).decode("ascii")
    except Exception:
        return None


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
        report_runs = [self._run_summary(run) for run in runs]
        detailed_runs = [self._run_detail(run, scenarios) for run in runs]
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
            detailed_runs=detailed_runs,
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

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _run_summary(self, run: ExecutionRun) -> dict:
        """One row in the overview table."""
        status = run.status.value if hasattr(run.status, "value") else str(run.status)
        return {
            "id": run.id,
            "scenario_id": run.scenario_id,
            "created_by": run.created_by or "",
            "status": status,
            "score": run.verdict.score if run.verdict else "",
            "failure_reason": run.failure_reason or "",
            "duration_seconds": run.metrics.duration_seconds if run.metrics.duration_seconds is not None else "",
        }

    def _run_detail(self, run: ExecutionRun, scenarios: list[TestScenario]) -> dict:
        """Full detail block for one run — actions, screenshots, traces."""
        scenario_title = run.scenario_id
        for scenario in scenarios:
            if scenario.id == run.scenario_id:
                scenario_title = scenario.title
                break
        status = run.status.value if hasattr(run.status, "value") else str(run.status)
        actions = []
        for action in run.actions:
            actions.append({
                "index": action.index,
                "tool": action.tool if hasattr(action.tool, "value") else str(action.tool),
                "thought": action.thought,
                "observation": action.observation or "",
                "error": action.error or "",
                "status": action.status.value if hasattr(action.status, "value") else str(action.status),
                "screenshot_base64": _read_screenshot_base64(action.screenshot_path),
            })

        return {
            "id": run.id,
            "scenario_title": scenario_title,
            "created_by": run.created_by or "",
            "status": status,
            "viewport": run.metrics.viewport,
            "duration_seconds": run.metrics.duration_seconds if run.metrics.duration_seconds is not None else "",
            "action_count": run.metrics.action_count,
            "passed_actions": run.metrics.passed_actions,
            "verdict_error_types": run.verdict.error_types if run.verdict else [],
            "traces": run.trace[-12:],  # last 12 trace entries
            "actions": actions,
        }
