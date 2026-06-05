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
  <p>{{ error_counts }}</p>
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
        error_counter = Counter(
            error
            for run in runs
            if run.verdict
            for error in run.verdict.error_types
        )
        html = Template(REPORT_TEMPLATE).render(
            generated_at=datetime.now(UTC).isoformat(),
            coverage=coverage,
            runs=report_runs,
            error_counts=dict(error_counter),
        )
        html_path = self.settings.reports_dir / f"{report_id}.html"
        json_path = self.settings.reports_dir / f"{report_id}.json"
        html_path.write_text(html, encoding="utf-8")
        json_path.write_text(
            json.dumps(
                {
                "coverage": coverage.model_dump(mode="json"),
                "runs": [run.model_dump(mode="json", exclude_none=True) for run in runs],
                "error_counts": dict(error_counter),
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
