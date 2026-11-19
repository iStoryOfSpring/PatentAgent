#!/usr/bin/env bash
# Local single-process development launcher.
set -eu
cd "$(dirname "$0")"
ROOT=$(pwd -P)
DATA_DIR=${MCP_INPUT_DIR:-$ROOT/my_patents}
BACKEND_PORT=${PATENTAGENT_BACKEND_PORT:-8000}
FRONTEND_PORT=${PATENTAGENT_FRONTEND_PORT:-5173}
BACKEND_URL="http://127.0.0.1:$BACKEND_PORT"
FRONTEND_URL="http://127.0.0.1:$FRONTEND_PORT"
backend_pid=
frontend_pid=

cleanup() {
    for pid in "$frontend_pid" "$backend_pid"; do
        if [ -n "$pid" ]; then kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; fi
    done
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
fail() { echo "$*" >&2; exit 1; }

command -v uv >/dev/null || fail "缺少 uv。安装 uv 后运行 uv sync --frozen --extra mcp --group dev"
[ -x "$ROOT/.venv/bin/python" ] || fail "缺少项目环境。请运行 uv sync --frozen --extra mcp --group dev"
PYTHON=$(uv run --frozen --no-sync python -c 'import fastapi, uvicorn, sys; print(sys.executable)') || fail "后端依赖缺失。请运行 uv sync --frozen --extra mcp --group dev"
VITE="$ROOT/frontend/node_modules/.bin/vite"
[ -x "$VITE" ] || fail "前端依赖缺失。请在 frontend/ 运行 npm ci"

port_busy() {
    "$PYTHON" -c 'import socket,sys
with socket.socket() as sock:
    sock.settimeout(0.3)
    sys.exit(sock.connect_ex(("127.0.0.1",int(sys.argv[1]))) != 0)' "$1"
}
healthy() {
    curl --noproxy '*' -fsS --max-time 1 "$BACKEND_URL/api/health" 2>/dev/null |
        "$PYTHON" -c 'import json,sys
try: data=json.load(sys.stdin)
except ValueError: sys.exit(1)
sys.exit(data.get("application") != "PatentAgent" or data.get("status") != "ok")'
}
port_busy "$FRONTEND_PORT" && fail "前端端口 $FRONTEND_PORT 已占用"
if port_busy "$BACKEND_PORT"; then
    healthy || fail "后端端口 $BACKEND_PORT 被其他服务或旧版本占用"
    [ "${PATENTAGENT_REQUIRE_NEW_BACKEND:-0}" != 1 ] || fail "验收需要独立后端；端口 $BACKEND_PORT 已占用"
    echo "复用 PatentAgent 后端 $BACKEND_URL"
else
    MCP_INPUT_DIR="$DATA_DIR" PATENT_DATA_ROOT="${PATENT_DATA_ROOT:-$DATA_DIR}" "$PYTHON" -m uvicorn server:app --host 127.0.0.1 --port "$BACKEND_PORT" &
    backend_pid=$!
fi
(cd frontend && export VITE_API_TARGET="$BACKEND_URL" && exec "$VITE" --host 127.0.0.1 --strictPort --port "$FRONTEND_PORT") &
frontend_pid=$!
deadline=$((SECONDS + 30))
while true; do
    if [ -n "$backend_pid" ]; then kill -0 "$backend_pid" 2>/dev/null || fail "后端提前退出"; fi
    kill -0 "$frontend_pid" 2>/dev/null || fail "前端提前退出"
    if healthy && curl --noproxy '*' -fsS --max-time 1 "$FRONTEND_URL/" >/dev/null 2>&1; then break; fi
    if [ "$SECONDS" -ge "$deadline" ]; then
        healthy || fail "后端在 30 秒内未就绪"
        fail "前端在 30 秒内未就绪"
    fi
    sleep 0.25
done
echo "PatentAgent 已启动  前端 $FRONTEND_URL  后端 $BACKEND_URL"
if [ "${PATENTAGENT_OPEN_BROWSER:-1}" != 0 ]; then
    if command -v open >/dev/null; then open "$FRONTEND_URL"
    elif command -v xdg-open >/dev/null; then xdg-open "$FRONTEND_URL"; fi
fi
while kill -0 "$frontend_pid" 2>/dev/null; do
    if [ -n "$backend_pid" ]; then kill -0 "$backend_pid" 2>/dev/null || fail "后端已退出"; fi
    sleep 1
done
fail "前端已退出"
