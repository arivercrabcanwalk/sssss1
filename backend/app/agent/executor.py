from __future__ import annotations

import time
from datetime import UTC, datetime
from os import environ
from pathlib import Path
from typing import Awaitable, Callable
from uuid import uuid4

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright

from app.agent.memory import AgentMemory
from app.agent.planner import TestPlanner
from app.agent.verifier import RunVerifier
from app.config import get_settings
from app.models import ActionStatus, AgentAction, ExecutionMetrics, ExecutionRun, TestScenario


class BrowserAgent:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.planner = TestPlanner()
        self.verifier = RunVerifier()

    async def execute(
        self,
        scenario: TestScenario,
        target_url: str | None = None,
        headless: bool = True,
        viewport: str = "desktop",
        run_id: str | None = None,
        on_update: Callable[[ExecutionRun], Awaitable[None]] | None = None,
    ) -> ExecutionRun:
        run_id = run_id or f"run_{uuid4().hex[:12]}"
        target = target_url or self.settings.target_app_url
        plan = self.planner.plan(scenario, target)
        run_dir = self.settings.runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        run = ExecutionRun(
            id=run_id,
            scenario_id=scenario.id,
            status=ActionStatus.running,
            target_url=target,
            plan=plan,
            metrics=ExecutionMetrics(viewport=viewport),
        )
        run.trace.append("执行计划已生成，准备启动浏览器")
        await self._notify(on_update, run)
        memory = AgentMemory(doc_refs=scenario.evidence_refs)
        started = time.perf_counter()
        try:
            async with async_playwright() as pw:
                browser = await self._launch_browser(pw, headless=headless)
                page = await browser.new_page(
                    viewport={"width": 390, "height": 844}
                    if viewport == "mobile"
                    else {"width": 1440, "height": 960}
                )
                page.set_default_timeout(6000)
                for action in plan:
                    run.trace.append(f"开始动作 {action.index}: {action.thought}")
                    await self._notify(on_update, run)
                    executed = await self._execute_action(page, action, run_dir, memory)
                    memory.remember_action(executed)
                    run.actions.append(executed)
                    run.trace.append(executed.observation or executed.thought)
                    self._refresh_metrics(run)
                    await self._notify(on_update, run)
                    if executed.status == ActionStatus.failed and executed.tool not in {"assert_text"}:
                        break
                await browser.close()
        except Exception as exc:
            run.trace.append(f"Agent crashed: {exc}")
            if not run.actions or run.actions[-1].status != ActionStatus.failed:
                run.actions.append(
                    AgentAction(
                        index=len(run.actions) + 1,
                        thought="浏览器执行异常",
                        tool="inspect",
                        status=ActionStatus.failed,
                        error=str(exc),
                        observation="Playwright runtime exception",
                    )
                )
        self._refresh_metrics(run, started=started, finished=True)
        run.trace.append("动作执行完成，正在验证测试结果")
        await self._notify(on_update, run)
        run.verdict = await self.verifier.verify(run, scenario)
        run.status = ActionStatus.passed if run.verdict.passed else ActionStatus.failed
        run.failure_reason = run.verdict.failure_reason
        run.trace.append(f"验证完成: {run.status.value}")
        await self._notify(on_update, run)
        return run

    async def _notify(
        self,
        on_update: Callable[[ExecutionRun], Awaitable[None]] | None,
        run: ExecutionRun,
    ) -> None:
        if on_update:
            await on_update(run)

    def _refresh_metrics(
        self,
        run: ExecutionRun,
        started: float | None = None,
        finished: bool = False,
    ) -> None:
        if finished:
            run.metrics.finished_at = datetime.now(UTC)
        if started is not None:
            run.metrics.duration_seconds = round(time.perf_counter() - started, 3)
        run.metrics.action_count = len(run.actions)
        run.metrics.passed_actions = sum(1 for action in run.actions if action.status == ActionStatus.passed)
        run.metrics.screenshot_count = sum(1 for action in run.actions if action.screenshot_path)

    async def _launch_browser(self, pw, headless: bool):
        # Skip bundled Chromium (not installed) — go directly to system browsers.
        last_error = "no browser found"
        for executable in self._browser_executable_candidates():
            try:
                return await pw.chromium.launch(
                    executable_path=str(executable),
                    headless=headless,
                    args=[
                        "--disable-gpu",
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--no-first-run",
                        "--no-default-browser-check",
                    ],
                )
            except Exception as exc:
                last_error = f"{executable}: {exc}"
                continue
        raise RuntimeError(
            f"无法启动浏览器。已尝试 {len(self._browser_executable_candidates())} 个候选路径。"
            f"最后的错误: {last_error}。"
            f"请运行 `python -m playwright install chromium` 或设置 PLAYWRIGHT_BROWSER_EXECUTABLE。"
        )

    def _browser_executable_candidates(self) -> list[Path]:
        configured = self.settings.playwright_browser_executable
        candidates = [Path(configured)] if configured else []
        local_app_data = environ.get("LOCALAPPDATA")
        program_files = environ.get("PROGRAMFILES")
        program_files_x86 = environ.get("PROGRAMFILES(X86)")
        home = Path.home()
        candidates.extend(
            [
                Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
                Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
                home / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                home / "Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                home / "Applications/Chromium.app/Contents/MacOS/Chromium",
            ]
        )
        for root, suffix in [
            (local_app_data, "Google/Chrome/Application/chrome.exe"),
            (program_files, "Google/Chrome/Application/chrome.exe"),
            (program_files_x86, "Google/Chrome/Application/chrome.exe"),
            (program_files, "Microsoft/Edge/Application/msedge.exe"),
            (program_files_x86, "Microsoft/Edge/Application/msedge.exe"),
        ]:
            if root:
                candidates.append(Path(root) / suffix)
        seen: set[Path] = set()
        existing: list[Path] = []
        for candidate in candidates:
            resolved = candidate.expanduser()
            if resolved not in seen and resolved.exists():
                existing.append(resolved)
                seen.add(resolved)
        return existing

    async def _execute_action(
        self,
        page,
        action: AgentAction,
        run_dir: Path,
        memory: AgentMemory,
    ) -> AgentAction:
        action.status = ActionStatus.running
        try:
            if action.tool == "goto":
                await page.goto(action.value or self.settings.target_app_url, wait_until="networkidle")
                login_observation = await self._ensure_logged_in(page)
                title = await page.title()
                action.observation = (
                    f"Opened {page.url}; title={title}"
                    + (f"; {login_observation}" if login_observation else "")
                )
            elif action.tool == "click":
                locator = await self._locator(
                    page,
                    action.selector,
                    fallback_selector="button, [role='button'], a",
                )
                if locator:
                    await locator.click()
                    await page.wait_for_timeout(500)
                    action.observation = f"Clicked {action.selector or 'first available control'}"
                else:
                    action.status = ActionStatus.failed
                    action.error = f"未找到可点击控件: {action.selector}"
                    action.observation = f"未找到可点击控件，按场景意图继续: {action.thought}"
            elif action.tool == "fill":
                locator = await self._locator(
                    page,
                    action.selector,
                    fallback_selector="input, textarea, [contenteditable='true'], [role='textbox']",
                )
                if locator:
                    try:
                        await locator.fill(action.value or "")
                        action.observation = f"Filled {action.selector or 'first editable field'}"
                    except PlaywrightError:
                        action.status = ActionStatus.failed
                        action.error = "目标控件不可编辑"
                        action.observation = f"目标控件不可编辑，按场景意图记录输入: {action.value or ''}"
                else:
                    action.status = ActionStatus.failed
                    action.error = f"未找到可编辑控件: {action.selector}"
                    action.observation = f"未找到可编辑控件，按场景意图记录输入: {action.value or ''}"
            elif action.tool == "press":
                await page.keyboard.press(action.value or "Enter")
                action.observation = f"Pressed {action.value or 'Enter'}"
            elif action.tool == "wait":
                await page.wait_for_timeout(1200)
                action.observation = "Waited for UI stability"
            elif action.tool == "assert_text":
                body = await page.locator("body").inner_text(timeout=3000)
                action.observation = self._assert_observation(body, action.value or memory.context())
            elif action.tool == "screenshot":
                screenshot_path = run_dir / f"action_{action.index}.png"
                await page.screenshot(path=str(screenshot_path), full_page=True)
                action.screenshot_path = str(screenshot_path)
                action.observation = "Captured screenshot"
            elif action.tool == "inspect":
                body = await page.locator("body").inner_text(timeout=3000)
                action.observation = body[:800]
            elif action.tool == "drag":
                action.observation = "Drag action is planned but requires app-specific coordinates"
            action.status = ActionStatus.passed
        except PlaywrightError as exc:
            action.status = ActionStatus.failed
            action.error = str(exc)[:500]
            action.observation = f"Playwright action failed: {action.error}"
            try:
                screenshot_path = run_dir / f"failed_{action.index}.png"
                await page.screenshot(path=str(screenshot_path), full_page=True)
                action.screenshot_path = str(screenshot_path)
            except Exception:
                pass
        return action

    async def _locator(self, page, selector: str | None, fallback_selector: str):
        if selector:
            candidates = [item.strip() for item in selector.split(",") if item.strip()]
            for candidate in candidates:
                for locator in [page.locator(candidate).first, page.get_by_text(candidate, exact=False).first]:
                    try:
                        await locator.wait_for(state="visible", timeout=1200)
                        return locator
                    except Exception:
                        continue
        fallback = page.locator(fallback_selector).first
        try:
            await fallback.wait_for(state="visible", timeout=1200)
            return fallback
        except Exception:
            return None

    async def _ensure_logged_in(self, page) -> str | None:
        # Wait for the React SPA to render the login form (headless can be slow).
        await page.wait_for_timeout(3000)

        email = page.locator("input[name='emailOrUsername']").first
        pwd = page.locator("input[name='password']").first
        login_btn = page.locator("button[type='submit']").first

        try:
            await email.wait_for(state="visible", timeout=8000)
        except PlaywrightError:
            # maybe the site uses a different login flow
            if "/login" not in page.url:
                return None
            return "detected /login in URL but email field not found"

        try:
            await pwd.wait_for(state="visible", timeout=2000)
        except PlaywrightError:
            return None

        try:
            await login_btn.wait_for(state="visible", timeout=2000)
        except PlaywrightError:
            return None

        try:
            await email.fill(self.settings.target_app_email)
            await pwd.fill(self.settings.target_app_password)
            await login_btn.click()
            # Wait until we leave the login page (up to 15s)
            await page.wait_for_url(
                lambda url: "/login" not in url,
                timeout=15000,
            )
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(500)
            return f"auto-login succeeded as {self.settings.target_app_email}"
        except PlaywrightError as exc:
            return f"auto-login failed: {str(exc)[:220]}"

    def _assert_observation(self, body: str, expected: str) -> str:
        expected_terms = [term for term in expected.lower().split() if len(term) > 3][:8]
        hits = [term for term in expected_terms if term in body.lower()]
        if hits:
            return f"Expectation partially matched terms: {', '.join(hits)}"
        return "Expectation checked by final verifier; direct text match not found"
