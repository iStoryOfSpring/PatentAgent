"""Launch the checkout from an unrelated cwd and exercise it in Chromium."""
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main():
    frontend, backend = free_port(), free_port()
    while frontend == backend:
        backend = free_port()
    with tempfile.TemporaryDirectory(prefix="patent-offline-") as temp:
        data = Path(temp) / "data"
        data.mkdir()
        url = f"http://127.0.0.1:{frontend}"
        safe_keys = ("PATH", "HOME", "TMPDIR", "SYSTEMROOT", "PLAYWRIGHT_BROWSERS_PATH", "UV_CACHE_DIR", "CI")
        env = {key: os.environ[key] for key in safe_keys if key in os.environ}
        env.update(PATENTAGENT_OPEN_BROWSER="0", PATENTAGENT_REQUIRE_NEW_BACKEND="1",
                   PATENTAGENT_E2E_URL=url, PATENTAGENT_FRONTEND_PORT=str(frontend),
                   PATENTAGENT_BACKEND_PORT=str(backend), PATENT_DATA_ROOT=str(data),
                   MCP_INPUT_DIR=str(data), PATENTAGENT_SESSION_DB=str(Path(temp) / "sessions.db"),
                   HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", NO_PROXY="127.0.0.1,localhost")
        output = ROOT / "frontend" / "test-results"
        output.mkdir(exist_ok=True)
        # Playwright recreates its own output directory, so keep the service log alongside it.
        with (ROOT / "frontend" / "offline-service.log").open("w+") as log:
            process = subprocess.Popen(["bash", str(ROOT / "start.sh")], cwd=temp, env=env, stdout=log, stderr=subprocess.STDOUT)
            try:
                for _ in range(170):
                    if process.poll() is not None:
                        break
                    try:
                        with urllib.request.urlopen(url + "/api/health", timeout=1) as response:
                            import json
                            if json.load(response).get("application") == "PatentAgent":
                                break
                    except (OSError, ValueError):
                        pass
                    time.sleep(.2)
                else:
                    raise RuntimeError("Timed out waiting for offline services")
                if process.poll() is not None:
                    log.seek(0)
                    raise RuntimeError(log.read())
                subprocess.run(["npm", "run", "test:e2e"], cwd=ROOT / "frontend", env=env, check=True)
            finally:
                process.terminate()
                process.wait(timeout=20)


if __name__ == "__main__":
    main()
