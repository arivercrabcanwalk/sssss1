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

### macOS / Linux

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .[dev]
python -m playwright install chromium

cd frontend
npm install
cd ..

cp .env.example .env
python scripts/dev.py
```

### Windows PowerShell

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
当前 `.env.example` 默认测试官方 demo：`https://demo.4gaboards.com/`。

## 本地 4ga Boards

如果需要改为本机部署的 4ga Boards，可以启动 Docker Desktop，然后运行：

```powershell
python scripts/setup_4gaboards.py
```

脚本会拉取官方 `RARgames/4gaBoards` 仓库并尝试用 Docker Compose 启动。若 Docker daemon 未启动，脚本会给出明确提示。启动后把 `.env` 里的 `TARGET_APP_URL` 改成本机地址即可。

## LLM 配置

默认使用 MiniMax OpenAI-compatible 接口：

- `MINIMAX_API_KEY`
- `MINIMAX_BASE_URL=https://api.minimaxi.com/v1`
- `MINIMAX_MODEL=MiniMax-M3`

`.env.example` 已保留 OpenAI-compatible fallback 配置。密钥不会写入日志或仓库。

## 演示账号

- 普通用户：`user` / `user123`
- 管理员：`admin` / `admin123`

## 演示流程

1. 登录前端：`http://127.0.0.1:5173`。
2. 点击“抓文档”，从 `https://docs.4gaboards.com/` 获取用户手册内容。
3. 点击“建知识库”，构建 RAG 检索索引。
4. 点击“生成场景”，使用 MiniMax 生成并校验中文功能点和测试场景。
5. 在左侧选择功能点，确认中间区域有简单、中等、困难场景。
6. 点击场景卡片上的“变异”，生成边界输入、缺失必填、错误顺序、移动布局、重复提交等变异测试。
7. 点击播放按钮执行测试，右侧可实时看到规划、动作、观察和验证结论。
8. 点击“报告”导出 HTML/JSON 测试报告。

## 常用命令

```bash
python -m pytest -q
cd frontend && npm run build
python scripts/dev.py
```
