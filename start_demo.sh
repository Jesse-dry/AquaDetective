#!/usr/bin/env bash
# 一键启动评委演示:AquaDetective 前后端全栈启动
# 用法: ./start_demo.sh [--mock]
#   默认: 后端(FastAPI :8000) + 前端(Vite dev :5173)
#   --mock: 只起前端(VITE_MOCK=1),无需后端,推理流走 public/mock 回放
# 依赖已装好时跳过安装;首次运行会自动 pip install / npm install(WSL 用独立 npm-cli)

set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"

BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"
BACKEND_PORT=8000
FRONTEND_PORT=5173
MOCK=0
[[ "${1:-}" == "--mock" ]] && MOCK=1

# ---------- 工具函数 ----------
log()  { printf '\033[36m[启动]\033[0m %s\n' "$*"; }
ok()   { printf '\033[32m[就绪]\033[0m %s\n' "$*"; }
err()  { printf '\033[31m[失败]\033[0m %s\n' "$*" >&2; }

wait_http() { # url 名称 最大秒数
  local i=0
  until curl -s -o /dev/null --max-time 2 "$1"; do
    ((i+=1)) || true
    if (( i >= $3 )); then err "$2 启动超时(${3}s)"; return 1; fi
    sleep 1
  done
  ok "$2 已就绪: $1"
}

cleanup() {
  log "停止所有服务..."
  [[ -n "${BACK_PID:-}" ]] && kill "$BACK_PID" 2>/dev/null || true
  [[ -n "${FRONT_PID:-}" ]] && kill "$FRONT_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# ---------- 后端 ----------
if (( MOCK )); then
  log "Mock 模式:跳过后端"
else
  log "检查 Python 依赖..."
  if ! (cd "$BACKEND_DIR" && python -c "import fastapi, uvicorn" 2>/dev/null); then
    log "安装后端依赖(首次)..."
    (cd "$BACKEND_DIR" && pip install -e ".[dev]" -q)
  fi

  # 数据库不存在时自动构建(同 seed 可复现)
  if [[ ! -f "$BACKEND_DIR/data/aqua.db" ]]; then
    log "构建演示数据库..."
    (cd "$BACKEND_DIR" && python -m app.data.seed)
  fi

  if curl -s -o /dev/null --max-time 2 "http://localhost:$BACKEND_PORT/api/v1/events"; then
    ok "后端已在运行(端口 $BACKEND_PORT 复用)"
  else
    log "启动后端 FastAPI (端口 $BACKEND_PORT)..."
    (cd "$BACKEND_DIR" && exec python -m uvicorn app.main:app --port "$BACKEND_PORT") &
    BACK_PID=$!
    wait_http "http://localhost:$BACKEND_PORT/api/v1/events" "后端" 30
  fi
fi

# ---------- 前端 ----------
log "检查前端依赖..."
if [[ ! -f "$FRONTEND_DIR/node_modules/vite/bin/vite.js" ]]; then
  log "安装前端依赖(首次,WSL 需独立 npm-cli)..."
  if [[ ! -f /tmp/package/bin/npm-cli.js ]]; then
    curl -sL https://registry.npmjs.org/npm/-/npm-10.9.2.tgz | tar xz -C /tmp
  fi
  (cd "$FRONTEND_DIR" && node /tmp/package/bin/npm-cli.js install)
fi

if curl -s -o /dev/null --max-time 2 "http://localhost:$FRONTEND_PORT"; then
  ok "前端 dev server 已在运行(端口 $FRONTEND_PORT 复用)"
else
  if (( MOCK )); then
    log "启动前端(Mock 模式,端口 $FRONTEND_PORT)..."
    (cd "$FRONTEND_DIR" && exec env VITE_MOCK=1 node node_modules/vite/bin/vite.js --port "$FRONTEND_PORT") &
  else
    log "启动前端 dev server(端口 $FRONTEND_PORT)..."
    (cd "$FRONTEND_DIR" && exec node node_modules/vite/bin/vite.js --port "$FRONTEND_PORT") &
  fi
  FRONT_PID=$!
  wait_http "http://localhost:$FRONTEND_PORT" "前端" 30
fi

# ---------- 就绪 ----------
echo ""
ok "==================== 演示环境就绪 ===================="
if (( MOCK )); then
  ok "  前端(Mock): http://localhost:$FRONTEND_PORT"
else
  ok "  前端:       http://localhost:$FRONTEND_PORT"
  ok "  后端 API:   http://localhost:$BACKEND_PORT/api/v1"
  ok "  API 文档:   http://localhost:$BACKEND_PORT/docs"
fi
ok "  停止: Ctrl+C"
ok "======================================================"
echo ""

# 挂起等待退出信号
wait
