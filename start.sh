#!/bin/bash
# PatentAgent 一键启动脚本 — 同时启动后端 (FastAPI) 和前端 (Vite)
# 用法: bash start.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
DATA_DIR="${MCP_INPUT_DIR:-$SCRIPT_DIR/my_patents}"

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

cleanup() {
    echo ""
    echo -e "${BLUE}正在关闭服务...${NC}"
    if [ -n "${BACKEND_PID:-}" ]; then
        kill "$BACKEND_PID" 2>/dev/null || true
        wait "$BACKEND_PID" 2>/dev/null || true
    fi
    if [ -n "${FRONTEND_PID:-}" ]; then
        kill "$FRONTEND_PID" 2>/dev/null || true
        wait "$FRONTEND_PID" 2>/dev/null || true
    fi
    echo -e "${GREEN}PatentAgent 已停止${NC}"
    exit 0
}
trap cleanup SIGINT SIGTERM

# ── 检查依赖 ──
echo -e "${BLUE}检查 Python 依赖...${NC}"
python3 -c "import fastapi, uvicorn" 2>/dev/null || {
    echo -e "${RED}缺少依赖: pip install fastapi uvicorn${NC}"
    exit 1
}

if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
    echo -e "${BLUE}安装前端依赖 (首次运行)...${NC}"
    cd "$FRONTEND_DIR" && npm install --cache /tmp/npm-cache 2>/dev/null
fi

# ── 启动后端 ──
echo -e "${GREEN}启动后端 → http://localhost:8000${NC}"
echo -e "  API 文档: http://localhost:8000/docs"
echo -e "  数据目录: $DATA_DIR"
cd "$SCRIPT_DIR"
BACKEND_PID=""
if lsof -nP -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
    if curl -fsS http://127.0.0.1:8000/api/health 2>/dev/null | grep -q '"status":"ok"'; then
        echo -e "${BLUE}端口 8000 上已有可用的 PatentAgent 后端，本次直接复用。${NC}"
    else
        echo -e "${RED}端口 8000 已被其他进程占用，未自动终止该进程。${NC}"
        lsof -nP -iTCP:8000 -sTCP:LISTEN
        echo -e "${RED}请关闭上方进程，或确认已有 PatentAgent 后端后再运行 start.sh。${NC}"
        exit 1
    fi
else
    MCP_INPUT_DIR="$DATA_DIR" PATENT_DATA_ROOT="$DATA_DIR" python3 -m uvicorn server:app --host 127.0.0.1 --port 8000 &
    BACKEND_PID=$!
    sleep 2

    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo -e "${RED}后端启动失败，请检查错误信息${NC}"
        exit 1
    fi
fi

# ── 启动前端 ──
echo -e "${GREEN}启动前端 → http://localhost:5173${NC}"
cd "$FRONTEND_DIR"
npx vite --host 127.0.0.1 --port 5173 &
FRONTEND_PID=$!
sleep 2

echo ""
echo -e "${GREEN}══════════════════════════════════════════${NC}"
echo -e "${GREEN}  PatentAgent 已启动${NC}"
echo -e "${GREEN}  前端: http://localhost:5173${NC}"
echo -e "${GREEN}  后端: http://localhost:8000${NC}"
echo -e "${GREEN}  API文档: http://localhost:8000/docs${NC}"
echo -e "${GREEN}  按 Ctrl+C 停止所有服务${NC}"
echo -e "${GREEN}══════════════════════════════════════════${NC}"

# ── 自动打开浏览器 ──
sleep 1
if command -v open &>/dev/null; then
    open http://localhost:5173
elif command -v xdg-open &>/dev/null; then
    xdg-open http://localhost:5173
fi

# ── 等待退出 ──
wait
