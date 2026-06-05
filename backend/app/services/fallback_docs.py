from __future__ import annotations

from datetime import UTC, datetime

from app.models import DocPage


def fallback_docs() -> list[DocPage]:
    """Small offline seed so the system remains demonstrable if docs crawling is unavailable."""
    pages = [
        (
            "Getting Started",
            "https://docs.4gaboards.com/docs/intro/",
            """
            4ga Boards is a project management application for boards, tasks, cards, collaboration,
            and workflow organization. Users can create projects, open boards, manage cards,
            collaborate with team members, and track work visually.
            """,
            ["Getting Started"],
        ),
        (
            "Projects",
            "https://docs.4gaboards.com/docs/project/",
            """
            Projects group boards and work items. A user can create a project, name it,
            open project settings, invite members, and manage project-level data. The project
            list should show newly created projects and allow navigation into project boards.
            """,
            ["Projects"],
        ),
        (
            "Boards",
            "https://docs.4gaboards.com/docs/board/",
            """
            Boards organize work in visual columns. Users can create boards inside a project,
            add lists or columns, create cards, move cards between columns, and inspect board
            activity. Board state should update after card creation or movement.
            """,
            ["Boards"],
        ),
        (
            "Cards",
            "https://docs.4gaboards.com/docs/card/",
            """
            Cards represent individual tasks. Users can add a card title and description,
            assign labels, due dates, comments, attachments, checklist items, and assignees.
            Saving a card should make it visible on the board and preserve edited content.
            """,
            ["Cards"],
        ),
        (
            "List View",
            "https://docs.4gaboards.com/docs/list-view/",
            """
            List view displays cards in a table-like view. Users can search, filter, sort,
            and inspect card fields. Filtered results should match the search criteria and
            sorting should change the visible order or sorting indicator.
            """,
            ["List View"],
        ),
        (
            "Import Export",
            "https://docs.4gaboards.com/docs/import-export/",
            """
            Import and export features allow users to move board data in or out of the system.
            The application should validate imported files, show errors for invalid input,
            and generate downloadable exports for supported data.
            """,
            ["Import Export"],
        ),
    ]
    return [
        DocPage(
            id=f"fallback_{idx}",
            title=title,
            url=url,
            content=content.strip(),
            headings=headings,
            crawled_at=datetime.now(UTC),
        )
        for idx, (title, url, content, headings) in enumerate(pages, 1)
    ]
