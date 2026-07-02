import type { ExecutionRun, FeaturePoint, Metrics, TestScenario } from "./types";

const jsonHeaders = { "Content-Type": "application/json" };

function backendOrigin() {
  if (window.location.port === "5173") {
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }
  return window.location.origin;
}

function apiUrl(path: string) {
  return path.startsWith("http") ? path : `${backendOrigin()}${path}`;
}

function wsUrl(path: string) {
  const url = new URL(path, backendOrigin());
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function request<T>(url: string, options?: RequestInit & { timeoutMs?: number }): Promise<T> {
  const timeoutMs = options?.timeoutMs ?? 30000;
  const controller = timeoutMs > 0 ? new AbortController() : undefined;
  const timeout = controller ? window.setTimeout(() => controller.abort(), timeoutMs) : undefined;
  const { timeoutMs: _timeoutMs, signal, ...fetchOptions } = options ?? {};
  const response = await fetch(apiUrl(url), {
    ...fetchOptions,
    signal: signal ?? controller?.signal
  })
    .catch((error) => {
      if (error instanceof DOMException && error.name === "AbortError") {
        throw new Error(`请求超时：本次操作超过 ${Math.round(timeoutMs / 1000)} 秒，已自动取消`);
      }
      throw error;
    })
    .finally(() => {
      if (timeout !== undefined) {
        window.clearTimeout(timeout);
      }
    });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.json() as Promise<T>;
}

async function pollRun(runId: string, onRun: (run: ExecutionRun) => void): Promise<ExecutionRun> {
  const startedAt = Date.now();
  while (Date.now() - startedAt < 300000) {
    const { run } = await request<{ run: ExecutionRun }>(`/api/runs/${runId}`, { timeoutMs: 15000 });
    onRun(run);
    if (run.status === "passed" || run.status === "failed") {
      return run;
    }
    await sleep(1000);
  }
  throw new Error("执行仍在运行：已切换轮询 5 分钟但尚未结束");
}

export const api = {
  health: () => request<Record<string, unknown>>("/api/health"),
  crawl: () =>
    request<{ count: number; cached: boolean }>("/api/docs/crawl", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ refresh: false, max_pages: 120 })
    }),
  buildKnowledge: () =>
    request<{ chunk_count: number }>("/api/knowledge/build", {
      method: "POST"
    }),
  generate: () =>
    request<{ features: FeaturePoint[]; scenarios: TestScenario[]; coverage: Metrics["coverage"] }>(
      "/api/scenarios/generate",
      {
        method: "POST",
        headers: jsonHeaders,
        body: JSON.stringify({ max_features: 6, scenarios_per_feature: 3, use_llm: true }),
        timeoutMs: 0
      }
    ),
  features: () => request<{ features: FeaturePoint[] }>("/api/features"),
  scenarios: () => request<{ scenarios: TestScenario[] }>("/api/scenarios"),
  metrics: () => request<Metrics>("/api/metrics"),
  getRun: (runId: string) => request<{ run: ExecutionRun }>(`/api/runs/${runId}`),
  mutate: (scenarioId: string) =>
    request<{ mutations: TestScenario[]; added_count: number; existing_count: number; scenario_count: number }>(
      `/api/scenarios/${scenarioId}/mutations`,
      {
        method: "POST",
        headers: jsonHeaders,
        body: JSON.stringify({
          mutation_types: ["boundary_input", "missing_required", "wrong_order", "mobile_layout", "duplicate_submit"]
        })
      }
    ),
  run: (scenarioIds: string[], viewport: "desktop" | "mobile") =>
    request<{ runs: ExecutionRun[] }>("/api/runs", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ scenario_ids: scenarioIds, headless: true, viewport, repeat: 1 })
    }),
  subscribeRun: (runId: string, onRun: (run: ExecutionRun) => void) =>
    new Promise<ExecutionRun>((resolve, reject) => {
      let settled = false;
      const socket = new WebSocket(wsUrl(`/api/runs/${runId}/events`));
      socket.onmessage = (event) => {
        const payload = JSON.parse(event.data) as
          | { type: "trace" | "done"; run: ExecutionRun }
          | { type: "error"; message: string };
        if (payload.type === "error") {
          reject(new Error(payload.message));
          socket.close();
          return;
        }
        onRun(payload.run);
        if (payload.type === "done") {
          settled = true;
          resolve(payload.run);
          socket.close();
        }
      };
      socket.onerror = () => {
        socket.close();
        if (!settled) {
          pollRun(runId, onRun).then(resolve).catch(reject);
        }
      };
    }),
  report: () =>
    request<{ report_id: string; url: string; paths: Record<string, string> }>("/api/reports", {
      method: "POST"
    })
};
