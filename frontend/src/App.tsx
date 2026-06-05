import { useEffect, useMemo, useState } from "react";
import { BarChart3, Database, FileDown, Globe, Loader2, RefreshCw, Sparkles } from "lucide-react";
import { api } from "./api/client";
import type { ExecutionRun, FeaturePoint, Metrics, TestScenario } from "./api/types";
import { FeatureList } from "./components/FeatureList";
import { RunTimeline } from "./components/RunTimeline";
import { ScenarioList } from "./components/ScenarioList";
import { StatCard } from "./components/StatCard";

type LogItem = {
  id: string;
  text: string;
};

export function App() {
  const [features, setFeatures] = useState<FeaturePoint[]>([]);
  const [scenarios, setScenarios] = useState<TestScenario[]>([]);
  const [runs, setRuns] = useState<ExecutionRun[]>([]);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [selectedFeatureId, setSelectedFeatureId] = useState<string>();
  const [selectedScenarioId, setSelectedScenarioId] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [busyLabel, setBusyLabel] = useState<string>();
  const [statusMessage, setStatusMessage] = useState("系统已就绪，可以按顶部按钮执行流水线");
  const [logs, setLogs] = useState<LogItem[]>([]);

  const selectedScenario = useMemo(
    () => scenarios.find((scenario) => scenario.id === selectedScenarioId),
    [scenarios, selectedScenarioId]
  );

  function log(text: string) {
    setStatusMessage(text);
    setLogs((items) => [{ id: crypto.randomUUID(), text }, ...items].slice(0, 8));
  }

  async function refresh(showMessage = false) {
    const [featureData, scenarioData, metricData] = await Promise.all([
      api.features(),
      api.scenarios(),
      api.metrics()
    ]);
    setFeatures(featureData.features);
    setScenarios(scenarioData.scenarios);
    setMetrics(metricData);
    if (!selectedFeatureId && featureData.features[0]) {
      setSelectedFeatureId(featureData.features[0].id);
    }
    if (!selectedScenarioId && scenarioData.scenarios[0]) {
      setSelectedScenarioId(scenarioData.scenarios[0].id);
    }
    if (showMessage) {
      log(
        `刷新完成：${featureData.features.length} 个功能点，${scenarioData.scenarios.length} 个场景，${metricData.run_count} 次执行`
      );
    }
  }

  async function guarded(label: string, action: () => Promise<void>) {
    setBusy(true);
    setBusyLabel(label);
    setStatusMessage(`${label}中...`);
    try {
      await action();
      await refresh();
    } catch (error) {
      log(error instanceof Error ? error.message : "操作失败");
    } finally {
      setBusy(false);
      setBusyLabel(undefined);
    }
  }

  useEffect(() => {
    refresh().catch(() => undefined);
  }, []);

  return (
    <main>
      <header className="topbar">
        <div>
          <h1>4ga Boards 智能测试平台</h1>
          <p>RAG 生成测试场景 · Web Agent 自主执行 · 变异与验证报告</p>
        </div>
        <div className="top-actions">
          <button
            disabled={busy}
            onClick={() =>
              guarded("抓取文档", async () => {
                log("开始抓取 4ga Boards 用户手册");
                const result = await api.crawl();
                log(`抓取完成：${result.count} 个文档页面${result.cached ? "（使用缓存）" : ""}`);
              })
            }
          >
            {busyLabel === "抓取文档" ? <Loader2 className="spin" size={16} /> : <Globe size={16} />}
            {busyLabel === "抓取文档" ? "抓取中" : "抓文档"}
          </button>
          <button
            disabled={busy}
            onClick={() =>
              guarded("构建知识库", async () => {
                log("开始构建 RAG 知识库");
                const result = await api.buildKnowledge();
                log(`知识库构建完成：${result.chunk_count} 个片段`);
              })
            }
          >
            {busyLabel === "构建知识库" ? <Loader2 className="spin" size={16} /> : <Database size={16} />}
            {busyLabel === "构建知识库" ? "构建中" : "建知识库"}
          </button>
          <button
            disabled={busy}
            onClick={() =>
              guarded("生成场景", async () => {
                log("开始从知识库生成结构化测试场景");
                const result = await api.generate();
                setFeatures(result.features);
                setScenarios(result.scenarios);
                log(`生成完成：${result.features.length} 个功能点，${result.scenarios.length} 个场景`);
              })
            }
          >
            {busyLabel === "生成场景" ? <Loader2 className="spin" size={16} /> : <Sparkles size={16} />}
            {busyLabel === "生成场景" ? "生成中" : "生成场景"}
          </button>
          <button
            disabled={busy}
            onClick={() =>
              guarded("生成报告", async () => {
                const result = await api.report();
                window.open(result.url, "_blank", "noopener,noreferrer");
                log(`报告已生成：${result.report_id}`);
              })
            }
          >
            {busyLabel === "生成报告" ? <Loader2 className="spin" size={16} /> : <FileDown size={16} />}
            {busyLabel === "生成报告" ? "导出中" : "报告"}
          </button>
          <button title="刷新" disabled={busy} onClick={() => guarded("刷新", () => refresh(true))}>
            {busy ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />}
          </button>
        </div>
      </header>

      <section className={`status-strip ${busy ? "busy" : ""}`}>
        {busy ? <Loader2 className="spin" size={16} /> : null}
        <span>{statusMessage}</span>
      </section>

      <section className="metrics-band">
        <StatCard label="功能点" value={metrics?.coverage.feature_count ?? features.length} hint="手册覆盖" />
        <StatCard label="测试场景" value={metrics?.coverage.scenario_count ?? scenarios.length} hint="含变异" />
        <StatCard label="通过率" value={`${Math.round((metrics?.pass_rate ?? 0) * 100)}%`} hint="执行稳定性" />
        <StatCard label="平均耗时" value={`${metrics?.avg_duration ?? 0}s`} hint="效率指标" />
        <div className="stat-card accent">
          <BarChart3 size={18} />
          <span>P0 {metrics?.coverage.p0_count ?? 0}</span>
          <strong>中高难 {metrics?.coverage.medium_or_hard_count ?? 0}</strong>
        </div>
      </section>

      <section className="workspace">
        <FeatureList
          features={features}
          selectedFeatureId={selectedFeatureId}
          onSelect={(id) => {
            setSelectedFeatureId(id);
            const scenario = scenarios.find((item) => item.feature_id === id);
            setSelectedScenarioId(scenario?.id);
          }}
        />
        <ScenarioList
          scenarios={scenarios}
          selectedFeatureId={selectedFeatureId}
          selectedScenarioId={selectedScenarioId}
          busy={busy}
          onSelect={setSelectedScenarioId}
          onMutate={(id) =>
            guarded("生成变异", async () => {
              const result = await api.mutate(id);
              log(`生成 ${result.mutations.length} 个变异场景`);
            })
          }
          onRun={(id, viewport) =>
            guarded("执行测试", async () => {
              log(`开始执行场景 ${id}`);
              const result = await api.run([id], viewport);
              setRuns((items) => [...result.runs, ...items]);
              log(`执行完成：${result.runs[0]?.status ?? "unknown"}`);
            })
          }
        />
        <RunTimeline runs={runs} />
      </section>

      <section className="detail-band">
        <div className="panel">
          <div className="panel-heading">
            <div>
              <h2>场景详情</h2>
              <p>证据引用、测试预言和预期状态</p>
            </div>
          </div>
          {selectedScenario ? (
            <div className="scenario-detail">
              <h3>{selectedScenario.title}</h3>
              <p>{selectedScenario.oracle}</p>
              <div className="detail-grid">
                {selectedScenario.expectations.map((item) => (
                  <div key={item.description}>
                    <strong>{item.severity}</strong>
                    <span>{item.description}</span>
                    <small>{item.observable}</small>
                  </div>
                ))}
              </div>
              <div className="evidence-list">
                {selectedScenario.evidence_refs.map((ref) => (
                  <a href={ref.url} key={ref.id} target="_blank" rel="noreferrer">
                    {ref.title}
                    <small>{ref.snippet}</small>
                  </a>
                ))}
              </div>
            </div>
          ) : (
            <div className="empty">生成场景后可查看详情</div>
          )}
        </div>
        <div className="panel log-panel">
          <div className="panel-heading">
            <div>
              <h2>操作日志</h2>
              <p>平台流水线状态</p>
            </div>
          </div>
          <div className="logs">
            {logs.length ? logs.map((item) => <div key={item.id}>{item.text}</div>) : <div>等待操作</div>}
          </div>
        </div>
      </section>
    </main>
  );
}
