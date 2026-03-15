from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .binance_client import BinanceBridge
from .config import settings
from .forwarder import N8NForwarder

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

forwarder = N8NForwarder(settings.n8n_webhook_url)
bridge = BinanceBridge(settings.binance_stream, forwarder)
bridge_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global bridge_task
    bridge_task = asyncio.create_task(bridge.run())
    try:
        yield
    finally:
        bridge.stop()
        if bridge_task:
            bridge_task.cancel()
        await forwarder.close()


app = FastAPI(title="VisuTrade Bridge Service", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "running": bridge.running,
        "stream": settings.binance_stream,
        "last_message_at": bridge.last_message_at.isoformat() if bridge.last_message_at else None,
    }
