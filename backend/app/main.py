from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.agent.executor import BrowserAgent
from app.auth import (
    LoginRequest,
    User,
    authenticate_user,
    create_access_token,
    get_current_user,
    require_admin,
    verify_ws_token,
)
from app.config import get_settings
from app.models import (
    ActionStatus,
    AppState,
    CrawlRequest,
    ExecutionMetrics,
    ExecutionRun,
    GenerateRequest,
    MutationRequest,
    RunRequest,
    TestScenario,
)
from app.rag.chunking import chunk_pages
from app.rag.crawler import DocsCrawler
from app.rag.retriever import HybridRetriever
from app.services.fallback_docs import fallback_docs
from app.services.mutator import ScenarioMutator
from app.services.reporter import Reporter
from app.services.scenario_generator import ScenarioGenerator
from app.storage import JsonStore


settings = get_settings()
store = JsonStore()
state: AppState = store.load_state()
retriever = HybridRetriever()
if state.chunks:
    retriever.build(state.chunks)
reporter = Reporter()
running_tasks: set[asyncio.Task] = set()

app = FastAPI(
    title="4ga Boards 智能测试场景生成与执行平台",
    description="RAG scenario generation, autonomous Playwright execution, mutation testing, and reports.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def save() -> None:
    store.save_state(state)


@app.post("/api/auth/login")
def auth_login(request: LoginRequest) -> dict:
    user = authenticate_user(request.username, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token(user)
    return {
        "access_token": token,
        "token_type": "bearer",
        "username": user.username,
        "role": user.role,
    }


@app.get("/api/auth/me")
def auth_me(current_user: User = Depends(get_current_user)) -> dict:
    return {"username": current_user.username, "role": current_user.role}


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "docs": len(state.docs),
        "chunks": len(state.chunks),
        "features": len(state.features),
        "scenarios": len(state.scenarios),
        "runs": len(state.runs),
        "llm_provider": settings.llm_provider,
        "llm_model": settings.openai_model,
        "target_app_url": settings.target_app_url,
    }


@app.post("/api/docs/crawl")
async def crawl_docs(request: CrawlRequest, _user: User = Depends(require_admin)) -> dict:
    if state.docs and not request.refresh:
        return {"count": len(state.docs), "docs": state.docs, "cached": True}
    crawler = DocsCrawler(str(request.base_url or settings.docs_base_url))
    docs = await crawler.crawl(max_pages=request.max_pages)
    if not docs:
        docs = fallback_docs()
    state.docs = docs
    state.chunks = []
    state.features = []
    state.scenarios = []
    save()
    store.write_json(settings.raw_dir / "docs.json", docs)
    return {"count": len(docs), "docs": docs, "cached": False}


@app.post("/api/knowledge/build")
async def build_knowledge(_user: User = Depends(require_admin)) -> dict:
    if not state.docs:
        state.docs = fallback_docs()
    state.chunks = chunk_pages(state.docs)
    count = retriever.build(state.chunks)
    save()
    store.write_json(settings.index_dir / "chunks.json", state.chunks)
    return {"chunk_count": count, "sample": state.chunks[:5]}


@app.post("/api/scenarios/generate")
async def generate_scenarios(request: GenerateRequest, _user: User = Depends(require_admin)) -> dict:
    if not state.chunks:
        await build_knowledge()
    generator = ScenarioGenerator(retriever)
    features, scenarios = await generator.generate(state.chunks, request)
    state.features = features
    state.scenarios = scenarios
    save()
    return {
        "features": features,
        "scenarios": scenarios,
        "coverage": reporter.coverage(features, scenarios),
    }


@app.get("/api/features")
def features(_user: User = Depends(get_current_user)) -> dict:
    return {"features": state.features}


@app.get("/api/scenarios")
def scenarios(_user: User = Depends(get_current_user)) -> dict:
    return {"scenarios": state.scenarios}


@app.get("/api/metrics")
def metrics(current_user: User = Depends(get_current_user)) -> dict:
    runs = _visible_runs(current_user)
    pass_count = sum(1 for run in runs if run.status == ActionStatus.passed)
    durations = [run.metrics.duration_seconds for run in runs if run.metrics.duration_seconds]
    return {
        "coverage": reporter.coverage(state.features, state.scenarios),
        "run_count": len(runs),
        "pass_count": pass_count,
        "pass_rate": round(pass_count / len(runs), 3) if runs else 0,
        "avg_duration": round(sum(durations) / len(durations), 3) if durations else 0,
    }


@app.post("/api/scenarios/{scenario_id}/mutations")
def mutate_scenario(scenario_id: str, request: MutationRequest, _user: User = Depends(get_current_user)) -> dict:
    scenario = next((item for item in state.scenarios if item.id == scenario_id), None)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    mutations = ScenarioMutator().mutate(scenario, request)
    existing_ids = {item.id for item in state.scenarios}
    added_count = 0
    for item in mutations:
        if item.id not in existing_ids:
            state.scenarios.append(item)
            existing_ids.add(item.id)
            added_count += 1
    save()
    return {
        "mutations": mutations,
        "added_count": added_count,
        "existing_count": len(mutations) - added_count,
        "scenario_count": len(state.scenarios),
    }


def _visible_runs(user: User) -> list[ExecutionRun]:
    """Admin sees all runs; regular users see only their own."""
    all_runs = list(state.runs.values())
    if user.role == "管理员":
        return all_runs
    return [r for r in all_runs if r.created_by == user.username]


@app.post("/api/runs")
async def create_runs(request: RunRequest, current_user: User = Depends(get_current_user)) -> dict:
    if not state.scenarios:
        raise HTTPException(status_code=400, detail="Generate scenarios before executing runs")
    selected = (
        [scenario for scenario in state.scenarios if scenario.id in set(request.scenario_ids or [])]
        if request.scenario_ids
        else state.scenarios[:1]
    )
    if not selected:
        raise HTTPException(status_code=404, detail="No matching scenarios")
    runs = []
    for scenario in selected:
        for _ in range(request.repeat):
            run_id = f"run_{uuid4().hex[:12]}"
            run = ExecutionRun(
                id=run_id,
                scenario_id=scenario.id,
                created_by=current_user.username,
                status=ActionStatus.running,
                target_url=str(request.target_url or settings.target_app_url),
                trace=["执行任务已创建，等待浏览器启动"],
                metrics=ExecutionMetrics(viewport=request.viewport),
            )
            state.runs[run.id] = run
            runs.append(run)
            task = asyncio.create_task(
                execute_run_task(
                    run_id,
                    scenario,
                    target_url=str(request.target_url or settings.target_app_url),
                    headless=request.headless,
                    viewport=request.viewport,
                )
            )
            running_tasks.add(task)
            task.add_done_callback(running_tasks.discard)
    save()
    return {"runs": runs}


async def execute_run_task(
    run_id: str,
    scenario: TestScenario,
    target_url: str,
    headless: bool,
    viewport: str,
) -> None:
    agent = BrowserAgent()

    async def persist(run: ExecutionRun) -> None:
        state.runs[run.id] = run
        save()

    try:
        run = await agent.execute(
            scenario,
            target_url=target_url,
            headless=headless,
            viewport=viewport,
            run_id=run_id,
            on_update=persist,
        )
        await persist(run)
    except Exception as exc:
        run = state.runs.get(run_id)
        if run:
            run.status = ActionStatus.failed
            run.failure_reason = str(exc)
            run.trace.append(f"执行任务异常: {exc}")
            await persist(run)


@app.get("/api/runs/{run_id}")
def get_run(run_id: str, current_user: User = Depends(get_current_user)) -> dict:
    run = state.runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if current_user.role != "管理员" and run.created_by != current_user.username:
        raise HTTPException(status_code=403, detail="无权查看此执行记录")
    return {"run": run}


@app.websocket("/api/runs/{run_id}/events")
async def run_events(websocket: WebSocket, run_id: str) -> None:
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001)
        return
    try:
        verify_ws_token(token)
    except HTTPException:
        await websocket.close(code=4001)
        return
    await websocket.accept()
    try:
        last_len = -1
        while True:
            run = state.runs.get(run_id)
            if not run:
                await websocket.send_json({"type": "error", "message": "Run not found"})
                return
            if len(run.trace) != last_len:
                await websocket.send_json({"type": "trace", "run": run.model_dump(mode="json")})
                last_len = len(run.trace)
            if run.status in {ActionStatus.passed, ActionStatus.failed}:
                await websocket.send_json({"type": "done", "run": run.model_dump(mode="json")})
                return
            await asyncio.sleep(0.5)
    finally:
        await websocket.close()


@app.get("/api/reports/{report_id}")
def get_report(report_id: str, current_user: User = Depends(get_current_user)) -> FileResponse:
    # Always regenerate with current user's visible runs to avoid cross-user caching.
    runs = _visible_runs(current_user)
    paths = reporter.write_report(report_id, state.features, state.scenarios, runs)
    report_path = Path(paths["html"])
    return FileResponse(report_path, media_type="text/html", filename=f"{report_id}.html")


@app.post("/api/reports")
def create_report(current_user: User = Depends(get_current_user)) -> dict:
    report_id = f"report_{uuid4().hex[:10]}"
    paths = reporter.write_report(report_id, state.features, state.scenarios, _visible_runs(current_user))
    return {"report_id": report_id, "paths": paths, "url": f"/api/reports/{report_id}"}


@app.post("/api/reset")
def reset_state(_user: User = Depends(require_admin)) -> dict:
    state.docs = []
    state.chunks = []
    state.features = []
    state.scenarios = []
    state.runs = {}
    save()
    return {"ok": True}


if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.api_host, port=settings.api_port, reload=True)
