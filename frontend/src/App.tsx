import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import {
  BarChart3,
  Database,
  FileDown,
  Globe,
  Loader2,
  LockKeyhole,
  LogOut,
  RefreshCw,
  Sparkles,
  UserRound
} from "lucide-react";
import { api, clearToken, getToken, setToken } from "./api/client";
import type { ExecutionRun, FeaturePoint, Metrics, TestScenario } from "./api/types";
import { FeatureList } from "./components/FeatureList";
import { RunTimeline } from "./components/RunTimeline";
import { ScenarioList } from "./components/ScenarioList";
import { StatCard } from "./components/StatCard";

type LogItem = {
  id: string;
  text: string;
};

type Account = {
  username: string;
  role: "普通用户" | "管理员";
};

export function App() {
  const [account, setAccount] = useState<Account | null>(() => {
    const token = getToken();
    if (!token) return null;
    try {
      const payload: { sub: string; role: string; exp: number } = JSON.parse(
        atob(token.split(".")[1])
      );
      if (payload.exp * 1000 < Date.now()) {
        clearToken();
        return null;
      }
      return { username: payload.sub, role: payload.role as Account["role"] };
    } catch {
      clearToken();
      return null;
    }
  });
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
  const [refreshCrawl, setRefreshCrawl] = useState(false);

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
    if (featureData.features[0]) {
      // Clear stale selection if current feature/scenario no longer exists
      if (!featureData.features.some((f) => f.id === selectedFeatureId)) {
        setSelectedFeatureId(featureData.features[0].id);
        setSelectedScenarioId(undefined);
      }
      if (scenarioData.scenarios[0]) {
        const exists = scenarioData.scenarios.some((s) => s.id === selectedScenarioId);
        if (!exists) {
          setSelectedScenarioId(scenarioData.scenarios[0].id);
        }
      }
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
    if (account) {
      refresh().catch(() => undefined);
    }
  }, [account]);

  function updateRun(run: ExecutionRun) {
    setRuns((items) => {
      const rest = items.filter((item) => item.id !== run.id);
      return [run, ...rest];
    });
  }

  if (!account) {
    return <LoginScreen onLogin={setAccount} />;
  }

  return (
    <main>
      <header className="topbar">
        <div>
          <h1>4ga Boards 智能测试平台</h1>
          <p>RAG 生成测试场景 · Web Agent 自主执行 · 变异与验证报告</p>
        </div>
        <div className="top-actions">
          <span className="session-chip">
            <UserRound size={15} />
            {account.role}
          </span>
          {account.role === "管理员" && (
            <button
              disabled={busy}
              onClick={() =>
                guarded("抓取文档", async () => {
                  log(refreshCrawl ? "开始强制重新抓取 4ga Boards 用户手册" : "开始抓取 4ga Boards 用户手册");
                  const result = await api.crawl(refreshCrawl);
                  log(`抓取完成：${result.count} 个文档页面${result.cached ? "（使用缓存）" : "（已重新抓取）"}`);
                })
              }
            >
              {busyLabel === "抓取文档" ? <Loader2 className="spin" size={16} /> : <Globe size={16} />}
              {busyLabel === "抓取文档" ? "抓取中" : "抓文档"}
            </button>
          )}
          {account.role === "管理员" && (
            <label className="crawl-refresh-toggle" title="勾选后忽略缓存，强制从官网重新抓取">
              <input
                type="checkbox"
                checked={refreshCrawl}
                onChange={(event) => setRefreshCrawl(event.target.checked)}
              />
              <span>强制刷新</span>
            </label>
          )}
          {account.role === "管理员" && (
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
          )}
          {account.role === "管理员" && (
            <button
              disabled={busy}
              onClick={() =>
                guarded("生成场景", async () => {
                  log("开始调用 MiniMax 生成结构化测试场景，复杂文档可能需要几分钟");
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
          )}
          <button
            disabled={busy}
            onClick={() =>
              guarded("生成报告", async () => {
                const result = await api.report();
                const html = await api.fetchReportHtml(result.url);
                const blob = new Blob([html], { type: "text/html" });
                const blobUrl = URL.createObjectURL(blob);
                window.open(blobUrl, "_blank", "noopener,noreferrer");
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
          <button
            title="退出登录"
            disabled={busy}
            onClick={() => {
              clearToken();
              setAccount(null);
              setRuns([]);
              log("已退出登录");
            }}
          >
            <LogOut size={16} />
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
              if (result.mutations[0]) {
                setSelectedScenarioId(result.mutations[0].id);
              }
              if (result.added_count > 0) {
                log(`变异测试已生成：新增 ${result.added_count} 个，已自动选中第一个变异场景`);
              } else if (result.existing_count > 0) {
                log(`该场景的 ${result.existing_count} 个变异测试已存在，已自动选中第一个变异场景`);
              } else {
                log("当前场景没有可生成的变异测试");
              }
            })
          }
          onRun={(id, viewport) =>
            guarded("执行测试", async () => {
              log(`开始执行场景 ${id}`);
              const result = await api.run([id], viewport);
              const started = result.runs[0];
              if (!started) {
                throw new Error("后端未返回执行任务");
              }
              updateRun(started);
              log(`执行任务已启动：${started.id}`);
              const finished = await api.subscribeRun(started.id, (run) => {
                updateRun(run);
                log(run.trace[run.trace.length - 1] ?? `执行状态：${run.status}`);
              });
              log(`执行完成：${finished.status}`);
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

const hints = [
  { username: "user", password: "user123", role: "普通用户" },
  { username: "admin", password: "admin123", role: "管理员" },
];

function LoginScreen({ onLogin }: { onLogin: (account: Account) => void }) {
  const [username, setUsername] = useState("user");
  const [password, setPassword] = useState("user123");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const result = await api.login(username, password);
      setToken(result.access_token);
      onLogin({ username: result.username, role: result.role });
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login-page">
      <form className="login-panel" onSubmit={submit}>
        <div className="login-mark">
          <LockKeyhole size={26} />
        </div>
        <h1>4ga Boards 智能测试平台</h1>
        <p>登录后进入测试场景生成与执行工作台</p>
        <label>
          <span>用户名</span>
          <input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" />
        </label>
        <label>
          <span>密码</span>
          <input
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            type="password"
            autoComplete="current-password"
          />
        </label>
        {error ? <div className="login-error">{error}</div> : null}
        <button type="submit" disabled={submitting}>
          {submitting ? "登录中..." : "登录"}
        </button>
        <div className="account-hints">
          {hints.map((item) => (
            <button
              type="button"
              key={item.username}
              onClick={() => {
                setUsername(item.username);
                setPassword(item.password);
                setError("");
              }}
            >
              {item.role}
            </button>
          ))}
        </div>
      </form>
    </main>
  );
}
