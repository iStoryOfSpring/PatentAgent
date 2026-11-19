"""Exercise launcher failures with disposable helper programs and loopback sockets."""
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys

import pytest


def executable(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + body + "\n")
    path.chmod(0o755)


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.mark.parametrize("failure,expected", [
    ("dependency", "前端依赖缺失"), ("backend_port", "被其他服务"),
    ("frontend_port", "前端端口"), ("vite_exit", "前端提前退出"),
])
def test_start_from_outside_project_reports_failures(tmp_path, failure, expected):
    project = tmp_path / "project"
    project.mkdir()
    script = project / "start.sh"
    shutil.copyfile(Path(__file__).resolve().parents[1] / "start.sh", script)
    python = project / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.symlink_to(sys.executable)
    executable(tmp_path / "bin/uv", 'test -f start.sh || exit 1\nprintf "%s\\n" "$TEST_PYTHON"')
    if failure != "dependency":
        executable(project / "frontend/node_modules/.bin/vite", "exit 4")
    # This local module substitutes for the heavyweight application during the early-exit case.
    (project / "uvicorn.py").write_text("import time\ntime.sleep(30)\n")
    backend_port, frontend_port = port(), port()
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        if failure == "backend_port":
            backend_port = occupied.getsockname()[1]
        if failure == "frontend_port":
            frontend_port = occupied.getsockname()[1]
        env = dict(os.environ, PATH=str(tmp_path / "bin") + ":" + os.environ["PATH"],
                   TEST_PYTHON=str(python), PATENTAGENT_OPEN_BROWSER="0",
                   PATENTAGENT_BACKEND_PORT=str(backend_port), PATENTAGENT_FRONTEND_PORT=str(frontend_port))
        result = subprocess.run(["bash", str(script)], cwd=tmp_path, env=env,
                                capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert expected in result.stderr
    assert "PatentAgent 已启动" not in result.stdout
