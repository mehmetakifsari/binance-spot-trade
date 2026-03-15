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

forwarder = N8NForwarder(settings.n8n_webhook_url) if settings.n8n_webhook_url else None
bridge = BinanceBridge(settings.binance_stream, forwarder) if forwarder else None
bridge_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global bridge_task
    if bridge:
        bridge_task = asyncio.create_task(bridge.run())
    else:
        logger.warning("N8N_WEBHOOK_URL is not set. Bridge stream worker is disabled.")
    try:
        yield
    finally:
        if bridge:
            bridge.stop()
        if bridge_task:
            bridge_task.cancel()
        if forwarder:
            await forwarder.close()


app = FastAPI(title="VisuTrade Bridge Service", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok" if bridge else "degraded",
        "running": bridge.running if bridge else False,
        "configured": bool(settings.n8n_webhook_url),
        "stream": settings.binance_stream,
        "last_message_at": bridge.last_message_at.isoformat() if bridge and bridge.last_message_at else None,
    }
