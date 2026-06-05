from __future__ import annotations

import asyncio

import httpx


async def main() -> int:
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=120) as client:
        health = (await client.get("/api/health")).json()
        print("health", health)
        crawl = (await client.post("/api/docs/crawl", json={"max_pages": 8, "refresh": False})).json()
        print("crawl", crawl["count"])
        knowledge = (await client.post("/api/knowledge/build")).json()
        print("chunks", knowledge["chunk_count"])
        generated = (
            await client.post(
                "/api/scenarios/generate",
                json={"max_features": 8, "scenarios_per_feature": 2, "use_llm": False},
            )
        ).json()
        print("features", len(generated["features"]), "scenarios", len(generated["scenarios"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
