export type DocRef = {
  id: string;
  title: string;
  url: string;
  heading?: string;
  snippet: string;
};

export type FeaturePoint = {
  id: string;
  name: string;
  description: string;
  priority: "P0" | "P1" | "P2";
  entities: string[];
  preconditions: string[];
  doc_refs: DocRef[];
};

export type TestStep = {
  index: number;
  action: string;
  target?: string;
  value?: string;
  expectation?: string;
};

export type TestExpectation = {
  description: string;
  observable: string;
  severity: "critical" | "major" | "minor";
};

export type TestScenario = {
  id: string;
  feature_id: string;
  title: string;
  difficulty: "simple" | "medium" | "hard";
  tags: string[];
  steps: TestStep[];
  expectations: TestExpectation[];
  oracle: string;
  evidence_refs: DocRef[];
  mutated_from?: string;
  mutation_type?: string;
};

export type AgentAction = {
  index: number;
  thought: string;
  tool: string;
  selector?: string;
  value?: string;
  status: "pending" | "running" | "passed" | "failed" | "skipped";
  observation?: string;
  screenshot_path?: string;
  error?: string;
};

export type ExecutionRun = {
  id: string;
  scenario_id: string;
  status: "pending" | "running" | "passed" | "failed" | "skipped";
  target_url: string;
  plan: AgentAction[];
  actions: AgentAction[];
  trace: string[];
  verdict?: {
    passed: boolean;
    score: number;
    failure_reason?: string;
    evidence: string[];
    error_types: string[];
  };
  failure_reason?: string;
  metrics: {
    duration_seconds?: number;
    action_count: number;
    passed_actions: number;
    screenshot_count: number;
    viewport: string;
  };
};

export type LoginRequest = {
  username: string;
  password: string;
};

export type LoginResponse = {
  access_token: string;
  token_type: string;
  username: string;
  role: "普通用户" | "管理员";
};

export type UserInfo = {
  username: string;
  role: "普通用户" | "管理员";
};

export type Metrics = {
  coverage: {
    feature_count: number;
    scenario_count: number;
    doc_ref_count: number;
    p0_count: number;
    medium_or_hard_count: number;
  };
  run_count: number;
  pass_count: number;
  pass_rate: number;
  avg_duration: number;
};
