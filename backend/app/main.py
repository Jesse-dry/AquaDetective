"""AquaDetective 后端入口。"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .data.seed import ensure_db
from .context import get_db_path, get_watershed
from .monitoring import MonitorService


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_db(settings)
    monitor_service = MonitorService(
        get_db_path(), get_watershed, enabled=settings.monitor_enabled,
        interval_s=settings.monitor_interval_s, window_h=settings.monitor_window_h,
        method=settings.monitor_method)
    _app.state.monitor = monitor_service
    monitor_service.start()
    try:
        yield
    finally:
        await asyncio.to_thread(monitor_service.stop)


app = FastAPI(title="AquaDetective Backend", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

from .api import investigate, monitor, report, series, simulate, watershed, ws  # noqa: E402

for mod in (watershed, series, simulate, investigate, monitor, report, ws):
    app.include_router(mod.router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok", "llm": bool(settings.llm_api_key)}
