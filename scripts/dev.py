from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def spawn(command: list[str], cwd: Path) -> subprocess.Popen:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "backend")
    return subprocess.Popen(command, cwd=str(cwd), env=env)


def main() -> int:
    backend = spawn([sys.executable, "-m", "uvicorn", "app.main:app", "--reload", "--host", "127.0.0.1", "--port", "8000"], ROOT / "backend")
    frontend = spawn(["npm", "run", "dev"], ROOT / "frontend")
    print("Backend: http://127.0.0.1:8000")
    print("Frontend: http://127.0.0.1:5173")
    try:
        backend.wait()
        frontend.wait()
    except KeyboardInterrupt:
        backend.terminate()
        frontend.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
