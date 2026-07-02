from __future__ import annotations

import re
from collections import defaultdict

from app.models import (
    DocRef,
    FeaturePoint,
    GenerateRequest,
    KnowledgeChunk,
    TestExpectation,
    TestScenario,
    TestStep,
)
from app.rag.chunking import extract_keywords, stable_id
from app.rag.retriever import HybridRetriever
from app.services.llm import LLMClient


FEATURE_HINTS = [
    ("project", "项目管理", ["project", "workspace", "create project", "member"]),
    ("board", "看板管理", ["board", "kanban", "view", "column"]),
    ("card", "卡片管理", ["card", "task", "description", "due date", "label"]),
    ("list", "列表视图", ["list view", "table", "filter", "sort"]),
    ("import_export", "导入导出", ["import", "export", "csv", "json"]),
    ("template", "模板与复制", ["template", "copy", "duplicate"]),
    ("comment", "评论与协作", ["comment", "mention", "activity"]),
    ("automation", "自动化与快捷操作", ["automation", "shortcut", "drag"]),
    ("account", "账户与权限", ["account", "login", "permission", "role"]),
]


class ScenarioGenerator:
    def __init__(self, retriever: HybridRetriever, llm: LLMClient | None = None) -> None:
        self.retriever = retriever
        self.llm = llm or LLMClient()

    async def generate(
        self,
        chunks: list[KnowledgeChunk],
        request: GenerateRequest,
    ) -> tuple[list[FeaturePoint], list[TestScenario]]:
        features = self._rule_features(chunks, request.max_features)
        if request.use_llm:
            features = await self._llm_refine_features(features, chunks, request.max_features)
        scenarios = self._rule_scenarios(features, request.scenarios_per_feature)
        if request.use_llm:
            scenarios = await self._llm_refine_scenarios(features, scenarios, request.scenarios_per_feature)
        return features, scenarios

    def _rule_features(self, chunks: list[KnowledgeChunk], max_features: int) -> list[FeaturePoint]:
        grouped: dict[str, list[KnowledgeChunk]] = defaultdict(list)
        for chunk in chunks:
            haystack = f"{chunk.title} {chunk.heading or ''} {' '.join(chunk.keywords)} {chunk.text}".lower()
            matched = False
            for key, _, hints in FEATURE_HINTS:
                if any(hint in haystack for hint in hints):
                    grouped[key].append(chunk)
                    matched = True
            if not matched:
                words = extract_keywords(f"{chunk.title} {chunk.text}", limit=3)
                if words:
                    grouped[words[0]].append(chunk)

        features: list[FeaturePoint] = []
        for key, default_name, _ in FEATURE_HINTS:
            refs = self._refs_from_chunks(grouped.get(key, []), limit=3)
            if refs:
                features.append(
                    FeaturePoint(
                        id=stable_id("feature", key),
                        name=default_name,
                        description=self._feature_description(default_name, refs),
                        doc_refs=refs,
                        priority="P0" if key in {"project", "board", "card"} else "P1",
                        entities=self._entities_for(key),
                        preconditions=["已登录 4ga Boards", "目标应用处于可访问状态"],
                    )
                )
        for key, group in grouped.items():
            if len(features) >= max_features:
                break
            if key in {hint[0] for hint in FEATURE_HINTS}:
                continue
            refs = self._refs_from_chunks(group, limit=2)
            if not refs:
                continue
            name = self._pretty_name(group[0].title or key)
            features.append(
                FeaturePoint(
                    id=stable_id("feature", key),
                    name=name,
                    description=self._feature_description(name, refs),
                    doc_refs=refs,
                    priority="P2",
                    entities=extract_keywords(" ".join(ref.snippet for ref in refs), limit=5),
                    preconditions=["已登录 4ga Boards"],
                )
            )
        return features[:max_features]

    async def _llm_refine_features(
        self,
        features: list[FeaturePoint],
        chunks: list[KnowledgeChunk],
        max_features: int,
    ) -> list[FeaturePoint]:
        evidence = "\n\n".join(
            f"[{chunk.id}] {chunk.title} {chunk.heading or ''}\n{chunk.text[:700]}" for chunk in chunks[:18]
        )
        fallback = {"features": [feature.model_dump(mode="json") for feature in features]}
        data = await self.llm.complete_json(
            system=(
                "你是软件测试专家。只能根据给定文档证据识别功能点。"
                "输出 JSON: {features:[{name,description,priority,entities,preconditions,source_ids}]}。"
                "除 source_ids 外，所有面向用户展示的字段必须使用简体中文。"
            ),
            user=(
                f"最多生成 {max_features} 个 4ga Boards 主要功能点。"
                "文档证据可能是英文，但功能名、描述、实体、前置条件必须翻译/概括为简体中文。"
                f"\n证据如下：\n{evidence}"
            ),
            fallback=fallback,
        )
        raw_features = data.get("features", []) if isinstance(data, dict) else []
        refined: list[FeaturePoint] = []
        chunk_by_id = {chunk.id: chunk for chunk in chunks}
        for item in raw_features[:max_features]:
            if not isinstance(item, dict):
                continue
            source_ids = item.get("source_ids") or []
            refs = self._refs_from_chunks([chunk_by_id[sid] for sid in source_ids if sid in chunk_by_id], 3)
            if not refs:
                refs = self.retriever.search(str(item.get("name", "")), 3)
            if not refs:
                continue
            refined.append(
                FeaturePoint(
                    id=stable_id("feature", str(item.get("name", ""))),
                    name=str(item.get("name") or "未命名功能"),
                    description=str(item.get("description") or "从用户手册中抽取的功能点"),
                    priority=item.get("priority") if item.get("priority") in {"P0", "P1", "P2"} else "P1",
                    entities=self._string_list(item.get("entities")),
                    preconditions=self._string_list(item.get("preconditions")) or ["已登录 4ga Boards"],
                    doc_refs=refs,
                )
            )
        if refined and self._feature_text_is_chinese(refined):
            return refined
        return features

    def _rule_scenarios(
        self,
        features: list[FeaturePoint],
        scenarios_per_feature: int,
    ) -> list[TestScenario]:
        scenarios: list[TestScenario] = []
        for feature in features:
            for idx in range(scenarios_per_feature):
                difficulty = "simple" if idx == 0 else "medium" if idx == 1 else "hard"
                variant = self._scenario_variant(feature, difficulty)
                scenario_id = stable_id("scenario", f"{feature.id}:{difficulty}:{variant['title']}")
                steps = [
                    TestStep(index=i + 1, action=step[0], target=step[1], value=step[2], expectation=step[3])
                    for i, step in enumerate(variant["steps"])
                ]
                expectations = [
                    TestExpectation(
                        description=str(variant["expectation"]),
                        observable=f"{feature.doc_refs[0].snippet[:180]} / {variant['observable']}",
                        severity="critical"
                        if feature.priority == "P0" and difficulty in {"simple", "hard"}
                        else "major",
                    )
                ]
                scenarios.append(
                    TestScenario(
                        id=scenario_id,
                        feature_id=feature.id,
                        title=f"{feature.name} - {variant['title']}",
                        difficulty=difficulty,
                        tags=[feature.priority, "rag", "manual-evidence", difficulty, str(variant["tag"])],
                        steps=steps,
                        expectations=expectations,
                        oracle=str(variant["oracle"]),
                        evidence_refs=feature.doc_refs,
                    )
                )
        return scenarios

    async def _llm_refine_scenarios(
        self,
        features: list[FeaturePoint],
        scenarios: list[TestScenario],
        scenarios_per_feature: int,
    ) -> list[TestScenario]:
        feature_payload = [
            {
                "id": feature.id,
                "name": feature.name,
                "description": feature.description,
                "evidence": [ref.snippet for ref in feature.doc_refs],
            }
            for feature in features[:10]
        ]
        fallback = {"scenarios": [scenario.model_dump(mode="json") for scenario in scenarios]}
        data = await self.llm.complete_json(
            system=(
                "你是 Web 测试架构师。根据功能点生成可由浏览器智能体执行的测试场景。"
                "输出 JSON: {scenarios:[{feature_id,title,difficulty,tags,steps,expectations,oracle}]}。"
                "除 feature_id、difficulty、tags、target、value、CSS selector 外，所有面向用户展示的字段必须使用简体中文。"
                "steps[].action 和 steps[].expectation 必须是中文动词短句，不要输出 navigate/click/type/assert 等英文动作名。"
            ),
            user=(
                f"每个功能生成 {scenarios_per_feature} 个场景。步骤字段为 action,target,value,expectation。"
                "必须可执行，必须包含预期状态。"
                "即使证据是英文，也要把标题、步骤、预期状态和测试预言写成简体中文。"
                f"\n功能点：{feature_payload}"
            ),
            fallback=fallback,
        )
        raw = data.get("scenarios", []) if isinstance(data, dict) else []
        features_by_id = {feature.id: feature for feature in features}
        refined: list[TestScenario] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            feature = features_by_id.get(item.get("feature_id"))
            if not feature:
                continue
            steps = self._normalize_steps(item.get("steps"))
            if not steps:
                continue
            expectations = self._normalize_expectations(item.get("expectations")) or [
                TestExpectation(
                    description="执行后应满足用户手册描述的功能状态",
                    observable=feature.doc_refs[0].snippet[:220],
                )
            ]
            refined.append(
                TestScenario(
                    id=stable_id("scenario", f"{feature.id}:{item.get('title')}:{len(refined)}"),
                    feature_id=feature.id,
                    title=str(item.get("title") or f"{feature.name}流程"),
                    difficulty=item.get("difficulty")
                    if item.get("difficulty") in {"simple", "medium", "hard"}
                    else "medium",
                    tags=self._string_list(item.get("tags")) or ["llm", "rag"],
                    steps=steps,
                    expectations=expectations,
                    oracle=str(item.get("oracle") or "根据步骤轨迹和预期状态验证是否成功"),
                    evidence_refs=feature.doc_refs,
                )
            )
        if (
            refined
            and self._scenario_text_is_chinese(refined)
            and self._scenario_difficulty_is_balanced(features, refined, scenarios_per_feature)
        ):
            return refined
        return scenarios

    def _has_cjk(self, text: object) -> bool:
        return bool(re.search(r"[\u4e00-\u9fff]", str(text)))

    def _feature_text_is_chinese(self, features: list[FeaturePoint]) -> bool:
        if not features:
            return False
        return all(self._has_cjk(feature.name) and self._has_cjk(feature.description) for feature in features)

    def _scenario_text_is_chinese(self, scenarios: list[TestScenario]) -> bool:
        if not scenarios:
            return False
        for scenario in scenarios:
            if not self._has_cjk(scenario.title) or not self._has_cjk(scenario.oracle):
                return False
            if not all(self._has_cjk(step.action) for step in scenario.steps):
                return False
            expectations = [step.expectation for step in scenario.steps if step.expectation]
            if expectations and not all(self._has_cjk(item) for item in expectations):
                return False
            if not all(self._has_cjk(item.description) for item in scenario.expectations):
                return False
        return True

    def _scenario_difficulty_is_balanced(
        self,
        features: list[FeaturePoint],
        scenarios: list[TestScenario],
        scenarios_per_feature: int,
    ) -> bool:
        expected = ["simple", "medium", "hard"][: max(1, min(scenarios_per_feature, 3))]
        for feature in features:
            difficulties = {
                scenario.difficulty
                for scenario in scenarios
                if scenario.feature_id == feature.id and not scenario.mutated_from
            }
            if not set(expected).issubset(difficulties):
                return False
        return True

    def _string_list(self, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [str(item) for item in value if item is not None]
        return [str(value)]

    def _normalize_steps(self, value: object) -> list[TestStep]:
        normalized: list[TestStep] = []
        raw_steps = value if isinstance(value, list) else [value] if value else []
        for index, step in enumerate(raw_steps, start=1):
            if isinstance(step, dict):
                normalized.append(
                    TestStep(
                        index=index,
                        action=str(step.get("action") or "inspect"),
                        target=str(step["target"]) if step.get("target") is not None else None,
                        value=str(step["value"]) if step.get("value") is not None else None,
                        expectation=str(step["expectation"])
                        if step.get("expectation") is not None
                        else None,
                    )
                )
            else:
                normalized.append(TestStep(index=index, action=str(step)))
        return normalized

    def _normalize_expectations(self, value: object) -> list[TestExpectation]:
        normalized: list[TestExpectation] = []
        raw_expectations = value if isinstance(value, list) else [value] if value else []
        for expectation in raw_expectations:
            if isinstance(expectation, dict):
                severity = expectation.get("severity")
                normalized.append(
                    TestExpectation(
                        description=str(expectation.get("description") or expectation),
                        observable=str(expectation.get("observable") or expectation.get("description") or expectation),
                        severity=severity if severity in {"critical", "major", "minor"} else "major",
                    )
                )
            else:
                text = str(expectation)
                normalized.append(TestExpectation(description=text, observable=text))
        return normalized

    def _refs_from_chunks(self, chunks: list[KnowledgeChunk], limit: int) -> list[DocRef]:
        refs: list[DocRef] = []
        seen: set[str] = set()
        for chunk in chunks:
            if chunk.id in seen:
                continue
            seen.add(chunk.id)
            refs.append(
                DocRef(
                    id=chunk.id,
                    title=chunk.title,
                    url=chunk.url,
                    heading=chunk.heading,
                    snippet=chunk.text[:420],
                )
            )
            if len(refs) >= limit:
                break
        return refs

    def _feature_description(self, name: str, refs: list[DocRef]) -> str:
        source = self._localized_doc_title(refs[0].title) if refs else "用户手册"
        return f"{name}功能来自{source}等用户手册证据，覆盖关键操作、结果状态和可验证页面表现。"

    def _localized_doc_title(self, title: str) -> str:
        mapping = {
            "Getting Started": "入门说明",
            "Projects": "项目说明",
            "Boards": "看板说明",
            "Cards": "卡片说明",
            "List View": "列表视图说明",
            "Import Export": "导入导出说明",
        }
        return mapping.get(title, title)

    def _pretty_name(self, text: str) -> str:
        text = re.sub(r"[-_]+", " ", text).strip()
        return text[:32] or "手册功能"

    def _entities_for(self, key: str) -> list[str]:
        mapping = {
            "project": ["Project", "Member", "Workspace"],
            "board": ["Board", "Column", "View"],
            "card": ["Card", "Label", "DueDate", "Assignee"],
            "list": ["ListView", "Filter", "Sort"],
            "import_export": ["ImportFile", "ExportFile"],
            "comment": ["Comment", "Activity"],
        }
        return mapping.get(key, ["User", "Board", "Card"])

    def _steps_for_feature(self, feature: FeaturePoint) -> list[tuple[str, str | None, str | None, str | None]]:
        name = feature.name
        if "项目" in name or "Project" in name:
            return [
                ("打开应用首页并登录", None, None, "进入项目列表或仪表盘"),
                ("点击新建项目入口", "button:has-text('New'), button:has-text('Create')", None, "出现项目表单"),
                ("填写项目名称", "input[name='name'], input[placeholder*='name']", "Auto Test Project", "名称被填入"),
                ("提交项目表单", "button[type='submit']", None, "项目出现在列表中"),
            ]
        if "看板" in name or "Board" in name:
            return [
                ("进入已有项目", "text=Project", None, "显示项目详情"),
                ("点击创建看板", "button:has-text('Board'), button:has-text('Create')", None, "出现看板创建入口"),
                ("填写看板名称", "input[name='name'], input[placeholder*='name']", "QA Board", "名称被填入"),
                ("提交并进入看板", "button[type='submit']", None, "出现看板列或卡片区域"),
            ]
        if "卡片" in name or "Card" in name:
            return [
                ("进入看板页面", "text=Board", None, "显示看板列"),
                ("点击添加卡片", "button:has-text('Card'), button:has-text('Add')", None, "出现卡片表单"),
                ("填写卡片标题", "input[name='title'], textarea", "Investigate generated scenario", "标题被填入"),
                ("保存卡片", "button[type='submit'], button:has-text('Save')", None, "新卡片出现在看板中"),
            ]
        if "列表" in name:
            return [
                ("进入列表视图", "text=List", None, "显示表格或列表"),
                ("执行筛选", "input[placeholder*='Search'], input[type='search']", "test", "列表根据关键字变化"),
                ("执行排序", "button:has-text('Sort'), [aria-label*='sort']", None, "列表顺序发生变化或排序状态高亮"),
            ]
        return [
            ("打开相关页面", None, None, f"页面包含{name}相关内容"),
            ("执行主要操作", "button, [role='button']", None, "操作被应用接收"),
            ("检查结果", None, None, "页面状态符合用户手册描述"),
        ]

    def _scenario_variant(self, feature: FeaturePoint, difficulty: str) -> dict[str, object]:
        if difficulty == "simple":
            return {
                "title": "基础创建流程",
                "tag": "happy-path",
                "steps": self._steps_for_feature(feature)[:3],
                "expectation": f"{feature.name}的基础操作可完成，页面进入预期状态",
                "observable": "关键页面、表单或列表状态发生正向变化",
                "oracle": "验证基础路径是否可达，动作是否被页面接收，关键状态是否出现。",
            }
        if difficulty == "medium":
            return self._medium_variant(feature)
        return self._hard_variant(feature)

    def _medium_variant(self, feature: FeaturePoint) -> dict[str, object]:
        name = feature.name
        if "项目" in name or "Project" in name:
            steps = [
                ("登录并进入项目列表", None, None, "显示项目列表或仪表盘"),
                ("创建带时间戳的项目", "button:has-text('New'), button:has-text('Create')", None, "出现项目表单"),
                ("填写项目名称", "input[name='name'], input[placeholder*='name']", "Auto Project Medium", "名称被填入"),
                ("保存项目", "button[type='submit'], button:has-text('Create'), button:has-text('Save')", None, "项目出现在列表中"),
                ("重新打开项目", "text=Auto Project Medium", None, "进入项目详情或看板区域"),
            ]
            title = "创建并回访流程"
        elif "看板" in name or "Board" in name:
            steps = [
                ("登录并进入项目", None, None, "项目区域可见"),
                ("创建新看板", "button:has-text('Board'), button:has-text('Create')", None, "出现看板表单"),
                ("填写看板名称", "input[name='name'], input[placeholder*='name']", "QA Regression Board", "名称被填入"),
                ("保存看板", "button[type='submit'], button:has-text('Save')", None, "看板进入可操作状态"),
                ("切换或打开看板视图", "text=QA Regression Board", None, "看板列区域可见"),
            ]
            title = "创建并进入看板流程"
        elif "卡片" in name or "Card" in name:
            steps = [
                ("进入看板页面", None, None, "看板列可见"),
                ("添加卡片", "button:has-text('Card'), button:has-text('Add')", None, "卡片表单可见"),
                ("填写卡片标题", "input[name='title'], textarea", "Medium Scenario Card", "标题被填入"),
                ("保存卡片", "button[type='submit'], button:has-text('Save')", None, "卡片显示在看板中"),
                ("再次打开卡片详情", "text=Medium Scenario Card", None, "详情弹窗或编辑区可见"),
            ]
            title = "创建并查看详情流程"
        elif "列表" in name:
            steps = [
                ("进入列表视图", "text=List", None, "列表视图可见"),
                ("输入搜索关键字", "input[placeholder*='Search'], input[type='search']", "Auto", "列表被过滤"),
                ("切换排序", "button:has-text('Sort'), [aria-label*='sort']", None, "排序状态变化"),
                ("清空筛选", "input[placeholder*='Search'], input[type='search']", "", "列表恢复显示"),
            ]
            title = "筛选排序组合流程"
        else:
            steps = [
                ("打开功能相关页面", None, None, f"显示{feature.name}相关区域"),
                ("执行主要操作", "button, [role='button']", None, "操作被接收"),
                ("执行第二个相关操作", "button, [role='button']", None, "页面状态继续变化"),
                ("检查结果一致性", None, None, "结果符合用户手册描述"),
            ]
            title = "组合操作流程"
        return {
            "title": title,
            "tag": "combined-flow",
            "steps": steps,
            "expectation": f"{feature.name}的组合操作可以保持状态一致并支持后续访问",
            "observable": "列表、详情、筛选或打开状态与操作一致",
            "oracle": "验证多步操作后数据是否保留、视图是否可访问、页面状态是否与预期一致。",
        }

    def _hard_variant(self, feature: FeaturePoint) -> dict[str, object]:
        name = feature.name
        if "项目" in name or "Project" in name:
            steps = [
                ("登录并打开新建项目表单", "button:has-text('New'), button:has-text('Create')", None, "项目表单出现"),
                ("提交空项目名称", "button[type='submit'], button:has-text('Create')", None, "系统阻止提交或提示必填"),
                ("输入超长项目名称", "input[name='name'], input[placeholder*='name']", "Auto Project " + "X" * 80, "输入被接收但布局不溢出"),
                ("连续点击保存两次", "button[type='submit'], button:has-text('Create'), button:has-text('Save')", None, "不会生成重复项目或执行异常"),
            ]
            title = "必填与重复提交异常流程"
        elif "看板" in name or "Board" in name:
            steps = [
                ("在移动视口打开看板入口", None, None, "导航和按钮可见"),
                ("创建空名称看板", "button:has-text('Board'), button:has-text('Create')", None, "系统提示必填或阻止保存"),
                ("输入超长看板名称", "input[name='name'], input[placeholder*='name']", "QA Board " + "Y" * 80, "页面不出现明显布局溢出"),
                ("检查看板入口仍可操作", "button, [role='button']", None, "关键控件仍可点击"),
            ]
            title = "移动端与边界名称流程"
        elif "卡片" in name or "Card" in name:
            steps = [
                ("进入看板并打开添加卡片", "button:has-text('Card'), button:has-text('Add')", None, "卡片表单可见"),
                ("保存空标题卡片", "button[type='submit'], button:has-text('Save')", None, "系统阻止空标题或给出提示"),
                ("输入包含特殊字符的标题", "input[name='title'], textarea", "Card !@#$%^&*() 边界测试", "内容被安全显示"),
                ("重复点击保存", "button[type='submit'], button:has-text('Save')", None, "不会创建重复卡片或崩溃"),
            ]
            title = "空标题与特殊字符流程"
        elif "列表" in name:
            steps = [
                ("进入列表视图", "text=List", None, "列表可见"),
                ("搜索不存在的关键字", "input[placeholder*='Search'], input[type='search']", "NO_MATCH_9999", "列表为空或显示无结果"),
                ("快速切换排序", "button:has-text('Sort'), [aria-label*='sort']", None, "排序不导致异常"),
                ("切换移动视口检查布局", None, None, "表格列不遮挡关键操作"),
            ]
            title = "无结果与布局稳定流程"
        else:
            steps = [
                ("打开功能页面", None, None, f"显示{feature.name}相关区域"),
                ("执行缺失输入的异常操作", "button, [role='button']", None, "系统给出错误提示或保持稳定"),
                ("执行边界输入", "input, textarea", "BOUNDARY_" + "Z" * 80, "页面不崩溃且无布局溢出"),
                ("重复执行提交操作", "button[type='submit'], button:has-text('Save')", None, "不会产生重复数据或异常"),
            ]
            title = "异常输入与稳定性流程"
        return {
            "title": title,
            "tag": "negative-boundary",
            "steps": steps,
            "expectation": f"{feature.name}在异常输入、重复操作或移动布局下仍保持稳定",
            "observable": "错误提示、阻止提交、无重复数据、无布局遮挡",
            "oracle": "验证异常路径是否被正确处理；执行异常、布局问题、语义错误或测试预言不匹配均判为失败。",
        }
