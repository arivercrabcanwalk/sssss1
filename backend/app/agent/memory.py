from __future__ import annotations

from dataclasses import dataclass, field

from app.models import AgentAction, DocRef


@dataclass
class AgentMemory:
    doc_refs: list[DocRef] = field(default_factory=list)
    page_summaries: list[str] = field(default_factory=list)
    failed_selectors: dict[str, int] = field(default_factory=dict)
    successful_patterns: list[str] = field(default_factory=list)

    def remember_action(self, action: AgentAction) -> None:
        if action.status == "failed" and action.selector:
            self.failed_selectors[action.selector] = self.failed_selectors.get(action.selector, 0) + 1
        if action.status == "passed" and action.selector:
            self.successful_patterns.append(action.selector)

    def context(self) -> str:
        snippets = [ref.snippet[:180] for ref in self.doc_refs[:4]]
        return "\n".join(snippets + self.page_summaries[-4:])
