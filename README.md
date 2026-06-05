# 4ga Boards 智能测试场景生成与执行平台

一个面向课程大作业的高复杂度实现：从 4ga Boards 用户手册自动抽取知识，生成带文档证据的结构化测试场景，并通过 Playwright + 大模型智能体执行、验证、变异测试，最终输出可视化报告。

## 功能覆盖

- 文档抓取：抓取 `https://docs.4gaboards.com/`，清洗页面并保存证据片段。
- RAG 知识库：Chroma 向量检索 + BM25 风格关键词检索兜底。
- 场景生成：生成 `FeaturePoint`、`TestScenario`，每个场景带 `doc_refs` / `evidence_refs`。
- 智能体执行：规划、记忆、浏览器执行、轨迹记录、规则验证与 LLM 验证。
- 创新扩展：测试场景变异、异常分类、布局检测、稳定性指标、HTML/JSON 报告。
- 可视化：React 仪表盘展示功能点、场景、运行轨迹、评估指标。

## 快速开始

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]
python -m playwright install chromium

cd frontend
npm install
cd ..

copy .env.example .env
python scripts/dev.py
```

后端默认运行在 `http://127.0.0.1:8000`，前端默认运行在 `http://127.0.0.1:5173`。

## 本地 4ga Boards

本机需要启动 Docker Desktop，然后运行：

```powershell
python scripts/setup_4gaboards.py
```

脚本会拉取官方 `RARgames/4gaBoards` 仓库并尝试用 Docker Compose 启动。若 Docker daemon 未启动，脚本会给出明确提示。

## LLM 配置

默认优先读取环境变量：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_MODEL`

也会尝试读取本机 Codex 配置中的 OpenAI Responses 兼容 provider。密钥不会写入日志或仓库。

## 常用命令

```powershell
pytest
python -m app.main
cd frontend; npm run dev
```

