# 4ga Boards 智能测试场景生成与执行平台

> 项目代码库：[https://github.com/arivercrabcanwalk/sssss1](https://github.com/arivercrabcanwalk/sssss1)  
> 应用访问地址：`http://127.0.0.1:5173`（前后端启动后）

面向课程大作业的实现：从 4ga Boards 用户手册自动抽取知识，生成带文档证据的结构化测试场景，通过 Playwright + 大模型智能体执行测试，支持变异测试与错误识别，最终输出可视化报告。

## 功能覆盖

- **文档抓取与清洗**：爬取 `https://docs.4gaboards.com/` 全部页面，去除导航、脚本、页脚等噪音，保留标题、正文和 URL 证据。
- **RAG 知识库**：ChromaDB 向量检索 + BM25 风格关键词检索双路召回，每个知识片段保留来源 URL。
- **场景生成**：规则引擎抽取功能点，LLM 精炼为结构化 `TestScenario`（步骤 + 预期状态 + 测试预言），每个场景带 `doc_refs` 文档证据。
- **智能体执行**：规划（`TestPlanner`）→ 记忆（`AgentMemory`）→ 浏览器执行（Playwright）→ 轨迹记录 → 验证（规则 + LLM 双重判定）。
- **变异测试**：支持边界输入、缺失必填、错误顺序、移动布局、重复提交 5 种变异。
- **错误识别**：自动识别执行异常、布局问题、语义错误、测试预言不匹配 4 类错误。
- **可视化面板**：React 仪表盘三栏展示功能点、场景、执行轨迹；WebSocket 实时推送执行进度。
- **HTML/JSON 报告**：每份报告包含功能覆盖表、执行概览表（标注执行者）、以及每个 Run 的详细动作步骤、截图和轨迹。

## 技术架构

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI + Uvicorn + Pydantic v2 |
| 浏览器自动化 | Playwright (Chromium) |
| LLM 集成 | OpenAI-compatible 接口（默认 MiniMax-M3，支持 DeepSeek 等） |
| 向量数据库 | ChromaDB（持久化存储） |
| 文档解析 | BeautifulSoup4 + httpx |
| 前端 | React 18 + TypeScript + Vite |
| 报告模板 | Jinja2 |
| 认证 | JWT (python-jose) + bcrypt 密码哈希 |
| 部署 | Docker Compose（后端 + Nginx 前端） |

## 演示账号与角色权限

| 角色 | 用户名 | 密码 | 权限 |
|------|--------|------|------|
| 管理员 | `admin` | `admin123` | 完整权限：抓取文档、构建知识库、生成测试场景、执行测试、生成变异、导出报告（含全局执行记录）、重置系统 |
| 普通用户 | `user` | `user123` | 受限权限：查看功能点/场景、执行测试、生成变异、导出报告（仅自己的执行记录） |

系统基于 JWT 实现认证，角色信息嵌入令牌。管理员负责搭建测试基础（文档→知识库→场景），普通用户在已有基础上执行测试和探索。执行报告按用户过滤，管理员可查看所有人的执行记录并标注执行者，普通用户仅见自己的记录。

## 演示流程

1. 登录前端 `http://127.0.0.1:5173`，使用管理员账号。
2. 点击"抓文档"，从 `https://docs.4gaboards.com/` 获取用户手册。
3. 点击"建知识库"，构建 RAG 检索索引。
4. 点击"生成场景"，使用 LLM 生成并校验中文功能点和测试场景（简单/中等/困难三层）。
5. 左侧选择功能点，中间区域查看对应场景。
6. 点击场景卡片"变异"按钮，生成 5 种变异测试。
7. 点击"播放"按钮执行测试，右侧实时展示规划、动作、观察和验证结论。
8. 点击"报告"导出 HTML 测试报告（含截图和轨迹详情）。

## 创新点与特色

- **RAG 文档证据可追溯**：每个功能点和场景均绑定来源文档 URL 和摘要，降低 LLM 幻觉风险。
- **混合检索 + 规则兜底**：向量检索 + 关键词检索双路召回，LLM 不可用时规则引擎自动兜底。
- **三层难度场景分层**：简单（基础路径）、中等（组合操作）、困难（异常边界），覆盖正向和负向测试。
- **5 种变异测试**：覆盖边界输入、必填缺失、操作乱序、移动布局、重复提交等典型异常场景。
- **实时执行轨迹**：WebSocket 实时推送每步动作状态，前端展示进度和最新截图。
- **按角色过滤报告**：管理员查看全局执行报告并标注执行者，普通用户仅见个人记录。

## 快速开始

### 准备工作

- Python 3.10+（[下载](https://www.python.org/downloads/)）
- Node.js 18+（[下载](https://nodejs.org/)）
- 4ga Boards 演示账号（在 `https://demo.4gaboards.com/` 注册）

### Windows PowerShell

```powershell
# 1. 允许脚本执行（首次需要，以管理员身份运行）
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# 2. 创建虚拟环境并安装依赖
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
python -m playwright install chromium   # 约 183MB，需良好网络

# 3. 安装前端依赖
cd frontend
npm install
cd ..

# 4. 配置环境变量
copy .env.example .env
# 用编辑器打开 .env，填入 MINIMAX_API_KEY（或 OPENAI_API_KEY）

# 5. 启动
python scripts/dev.py
```

> 若 Playwright Chromium 下载失败，可在 `.env` 中设置 `PLAYWRIGHT_BROWSER_EXECUTABLE` 指向系统 Chrome/Edge 路径。  
> 若 `python` 命令无效，尝试 `py` 或 `python3`。

### macOS / Linux

```bash
# 1. 创建虚拟环境并安装依赖
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
python -m playwright install chromium

# 2. 安装前端依赖
cd frontend
npm install
cd ..

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 MINIMAX_API_KEY（或 OPENAI_API_KEY）

# 4. 启动
python scripts/dev.py
```

后端 `http://127.0.0.1:8000`，前端 `http://127.0.0.1:5173`。默认测试 `https://demo.4gaboards.com/`。

## 本地 4ga Boards（可选）

如需本机部署目标应用，启动 Docker Desktop 后运行：

```powershell
python scripts/setup_4gaboards.py
```

脚本拉取 `RARgames/4gaBoards` 仓库并通过 Docker Compose 启动。启动后修改 `.env` 中 `TARGET_APP_URL` 为本机地址即可。

## LLM 配置

默认使用 MiniMax OpenAI-compatible 接口，在 `.env` 中配置：

- `MINIMAX_API_KEY` — MiniMax API 密钥
- `MINIMAX_BASE_URL` — 默认 `https://api.minimaxi.com/v1`
- `MINIMAX_MODEL` — 默认 `MiniMax-M3`

亦支持其他 OpenAI-compatible 提供商（OpenAI、DeepSeek 等），密钥不写入日志或仓库。

## 项目成员贡献说明

| 成员 | 开发任务 | 其他工作 | 贡献比 |
|------|---------|---------|--------|
| **张昊** | 项目架构设计、仓库初始化；FastAPI 后端框架搭建；LLM 模块（MiniMax 集成、OpenAI 兼容接口）；Docker 部署配置；代码审查合并 | 项目整体协调 | 18% |
| **刘桓** | JWT 认证与权限系统（`auth.py`）；前端登录页与角色 UI 控制；执行报告详细视图（动作步骤 + 截图 + 轨迹）；API 客户端 token 管理；强制刷新抓取功能 | 项目整体协调 | 17% |
| **信沛宏** | 前端仪表盘开发：`FeatureList`、`ScenarioList`、`RunTimeline` 组件；CSS 样式与响应式布局；WebSocket 实时执行轨迹展示 | 项目演示视频录制与讲解 | 16% |
| **刘德志** | 文档抓取器（`DocsCrawler` + `chunking.py`）；fallback 兜底文档；RAG 检索器（ChromaDB + BM25 关键词）；数据持久化（`JsonStore`） | 用户手册撰写 | 16% |
| **郭轩** | 场景生成器（规则引擎 + LLM 精炼 + 中文校验）；测试场景变异系统（5 种变异类型）；知识库构建流程 | 结题大报告撰写 | 16% |
| **张智棋** | Playwright 浏览器智能体（`executor.py`）；测试规划器（`planner.py`）与记忆模块（`memory.py`）；执行验证器（`RunVerifier`）；自动登录修复 | 结题大报告撰写 | 17% |

## 常用命令

```bash
python -m pytest -q            # 运行测试
cd frontend && npm run build   # 构建前端
python scripts/dev.py          # 一键启动前后端
```
