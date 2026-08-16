"""AquaDetective 后端入口。"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .data.seed import ensure_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_db(settings)
    yield


app = FastAPI(title="AquaDetective Backend", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

from .api import investigate, report, series, simulate, watershed, ws  # noqa: E402

for mod in (watershed, series, simulate, investigate, report, ws):
    app.include_router(mod.router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok", "llm": bool(settings.llm_api_key)}
