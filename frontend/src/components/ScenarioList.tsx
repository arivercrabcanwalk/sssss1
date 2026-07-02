import { FlaskConical, Play, Wand2 } from "lucide-react";
import type { TestScenario } from "../api/types";

type Props = {
  scenarios: TestScenario[];
  selectedFeatureId?: string;
  selectedScenarioId?: string;
  busy: boolean;
  onSelect: (id: string) => void;
  onRun: (id: string, viewport: "desktop" | "mobile") => void;
  onMutate: (id: string) => void;
};

export function ScenarioList({
  scenarios,
  selectedFeatureId,
  selectedScenarioId,
  busy,
  onSelect,
  onRun,
  onMutate
}: Props) {
  const visible = selectedFeatureId
    ? scenarios.filter((scenario) => scenario.feature_id === selectedFeatureId)
    : scenarios;
  const baseCount = visible.filter((scenario) => !scenario.mutated_from).length;
  const mutationCount = visible.length - baseCount;
  const mutationLabels: Record<string, string> = {
    boundary_input: "边界输入",
    missing_required: "缺失必填",
    wrong_order: "错误顺序",
    mobile_layout: "移动布局",
    duplicate_submit: "重复提交"
  };
  return (
    <section className="panel scenario-panel">
      <div className="panel-heading">
        <div>
          <h2>测试场景</h2>
          <p>
            结构化步骤、预期状态与测试预言 · 基础 {baseCount} 个 / 变异 {mutationCount} 个
          </p>
        </div>
        <FlaskConical size={20} />
      </div>
      <div className="scenario-list">
        {visible.map((scenario) => (
          <article
            className={`scenario-card ${selectedScenarioId === scenario.id ? "active" : ""}`}
            key={scenario.id}
            onClick={() => onSelect(scenario.id)}
          >
            <div className="scenario-top">
              <div>
                <strong>{scenario.title}</strong>
                <span className={`difficulty ${scenario.difficulty}`}>{scenario.difficulty}</span>
              </div>
              <div className="scenario-actions">
                <button
                  title="执行桌面测试"
                  disabled={busy}
                  onClick={(event) => {
                    event.stopPropagation();
                    onRun(scenario.id, "desktop");
                  }}
                >
                  <Play size={16} />
                </button>
                <button
                  className="mutate-button"
                  title="生成变异测试"
                  disabled={busy}
                  onClick={(event) => {
                    event.stopPropagation();
                    onMutate(scenario.id);
                  }}
                >
                  <Wand2 size={16} />
                  <span>变异</span>
                </button>
              </div>
            </div>
            {scenario.mutated_from ? (
              <div className="mutation-line">
                变异测试 · {mutationLabels[scenario.mutation_type ?? ""] ?? scenario.mutation_type ?? "自定义"}
              </div>
            ) : null}
            <ol>
              {scenario.steps.slice(0, 4).map((step) => (
                <li key={step.index}>
                  <span>{step.action}</span>
                  {step.expectation ? <small>{step.expectation}</small> : null}
                </li>
              ))}
            </ol>
            <div className="tag-line">
              {scenario.tags.slice(0, 5).map((tag) => (
                <span key={tag}>{tag}</span>
              ))}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
