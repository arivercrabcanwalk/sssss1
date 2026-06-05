# 架构设计

## 流水线

1. 文档抓取器从 4ga Boards 用户手册收集页面。
2. 清洗器去除导航、脚本、页脚，保留标题、正文和 URL。
3. 切块器按段落生成 `KnowledgeChunk`，保留 `page_id/title/url/heading`。
4. RAG 检索器构建 Chroma 向量索引，并提供关键词检索兜底。
5. 场景生成器先用规则抽取主功能，再让 LLM 细化；不可用时保留规则结果。
6. 智能体把 `TestScenario` 转成动作计划，Playwright 执行并记录截图、DOM 文本和错误。
7. 验证器用规则 + LLM 检查轨迹，输出通过率、失败原因和错误类型。
8. 前端展示功能点、证据、场景、变异、执行轨迹、指标和报告。

## 评分点映射

- 任务一：`DocsCrawler`、`HybridRetriever`、`ScenarioGenerator`、前端功能点/场景视图。
- 任务二：`TestPlanner`、`AgentMemory`、`BrowserAgent`、`RunVerifier`。
- 正确性：每个功能点和场景都必须带文档证据。
- 粒度与可执行性：场景拆分为步骤、目标、输入和预期状态。
- 稳定性：执行轨迹、失败截图、重复运行和通过率指标。
- 变异测试：边界输入、缺失必填项、错误顺序、移动布局、重复提交。
- 典型错误识别：执行异常、布局问题、语义错误、测试预言不匹配。

## 数据模型

- `FeaturePoint`: 功能点、优先级、实体、前置条件、文档证据。
- `TestScenario`: 步骤、预期、测试预言、证据引用、变异来源。
- `ExecutionRun`: 计划、动作、轨迹、验证结论、失败原因、指标。

## 演示建议

1. 启动 Docker Desktop。
2. 运行 `python scripts/setup_4gaboards.py`。
3. 启动平台 `python scripts/dev.py`。
4. 在前端依次点击抓文档、建知识库、生成场景。
5. 选择 P0 功能，展示证据引用和结构化测试场景。
6. 执行一个简单场景，再生成变异场景。
7. 导出报告，展示覆盖率、轨迹和失败原因。
