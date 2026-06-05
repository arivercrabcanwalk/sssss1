import type { ExecutionRun, FeaturePoint, Metrics, TestScenario } from "./types";

const jsonHeaders = { "Content-Type": "application/json" };

async function request<T>(url: string, options?: RequestInit & { timeoutMs?: number }): Promise<T> {
  const timeoutMs = options?.timeoutMs ?? 30000;
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  const { timeoutMs: _timeoutMs, signal, ...fetchOptions } = options ?? {};
  const response = await fetch(url, {
    ...fetchOptions,
    signal: signal ?? controller.signal
  })
    .catch((error) => {
      if (error instanceof DOMException && error.name === "AbortError") {
        throw new Error("请求超时：后端仍可用，但本次操作等待太久，已自动取消");
      }
      throw error;
    })
    .finally(() => window.clearTimeout(timeout));
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.json() as Promise<T>;
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
        body: JSON.stringify({ max_features: 20, scenarios_per_feature: 3, use_llm: false }),
        timeoutMs: 15000
      }
    ),
  features: () => request<{ features: FeaturePoint[] }>("/api/features"),
  scenarios: () => request<{ scenarios: TestScenario[] }>("/api/scenarios"),
  metrics: () => request<Metrics>("/api/metrics"),
  mutate: (scenarioId: string) =>
    request<{ mutations: TestScenario[]; scenario_count: number }>(`/api/scenarios/${scenarioId}/mutations`, {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({
        mutation_types: ["boundary_input", "missing_required", "mobile_layout", "duplicate_submit"]
      })
    }),
  run: (scenarioIds: string[], viewport: "desktop" | "mobile") =>
    request<{ runs: ExecutionRun[] }>("/api/runs", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ scenario_ids: scenarioIds, headless: true, viewport, repeat: 1 })
    }),
  report: () =>
    request<{ report_id: string; url: string; paths: Record<string, string> }>("/api/reports", {
      method: "POST"
    })
};
