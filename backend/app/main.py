"""AquaDetective 后端入口。"""
from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .data.seed import ensure_db
from .monitor_service import monitor_loop


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_db(settings)
    # 监测 Agent 后台定时扫描(可用 AQ_MONITOR_ENABLED=0 关闭,或前端状态条暂停)
    task = asyncio.create_task(monitor_loop())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="AquaDetective Backend", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

from .api import investigate, monitor, report, series, simulate, watershed, ws  # noqa: E402

for mod in (watershed, series, simulate, investigate, report, monitor, ws):
    app.include_router(mod.router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok", "llm": bool(settings.llm_api_key)}
