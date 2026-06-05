from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor"
REPO = VENDOR / "4gaBoards"


def run(command: list[str], cwd: Path = ROOT) -> int:
    print(" ".join(command))
    return subprocess.call(command, cwd=str(cwd))


def main() -> int:
    if run(["docker", "info"], ROOT) != 0:
        print("Docker daemon is not reachable. Start Docker Desktop and run this script again.")
        return 1
    VENDOR.mkdir(exist_ok=True)
    if not REPO.exists():
        code = run(["git", "clone", "https://github.com/RARgames/4gaBoards.git", str(REPO)], ROOT)
        if code != 0:
            return code
    compose_files = [REPO / "docker-compose.yml", REPO / "compose.yml", REPO / "docker-compose.yaml"]
    compose_file = next((item for item in compose_files if item.exists()), None)
    if not compose_file:
        print("No Docker Compose file found in 4gaBoards repository.")
        return 1
    return run(["docker", "compose", "-f", str(compose_file), "up", "-d"], REPO)


if __name__ == "__main__":
    raise SystemExit(main())
