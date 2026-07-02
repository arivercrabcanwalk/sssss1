import type { ExecutionRun, FeaturePoint, LoginResponse, Metrics, TestScenario, UserInfo } from "./types";

const TOKEN_KEY = "xdrj-token";

export function getToken(): string | null {
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  window.localStorage.removeItem(TOKEN_KEY);
}

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
  const { timeoutMs: _timeoutMs, signal, headers: optHeaders, ...fetchOptions } = options ?? {};

  const headers: Record<string, string> = { ...(optHeaders as Record<string, string> || {}) };
  const token = getToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(apiUrl(url), {
    ...fetchOptions,
    headers,
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
    if (response.status === 401 && !url.includes("/api/auth/login")) {
      clearToken();
      window.location.reload();
      throw new Error("登录已过期，请重新登录");
    }
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.json() as Promise<T>;
}

async function pollRun(runId: string, onRun: (run: ExecutionRun) => void): Promise<ExecutionRun> {
  const startedAt = Date.now();
  while (Date.now() - startedAt < 300000) {
    const data = await request<{ run: ExecutionRun }>(`/api/runs/${runId}`, { timeoutMs: 15000 });
    const run = data?.run;
    if (!run) {
      throw new Error("后端返回的执行数据异常");
    }
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
  login: (username: string, password: string) =>
    request<LoginResponse>("/api/auth/login", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ username, password }),
    }),
  me: () => request<UserInfo>("/api/auth/me"),
  crawl: (refresh = false) =>
    request<{ count: number; cached: boolean }>("/api/docs/crawl", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ refresh, max_pages: 120 })
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
        body: JSON.stringify({ max_features: 12, scenarios_per_feature: 3, use_llm: true }),
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
      const token = getToken();
      const socket = new WebSocket(
        `${wsUrl(`/api/runs/${runId}/events`)}?token=${encodeURIComponent(token ?? "")}`
      );
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
    }),
  fetchReportHtml: async (url: string): Promise<string> => {
    const headers: Record<string, string> = {};
    const token = getToken();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    const response = await fetch(apiUrl(url), { headers });
    if (!response.ok) {
      throw new Error("获取报告失败");
    }
    return response.text();
  }
};
