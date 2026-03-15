from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

import websockets
from websockets.client import WebSocketClientProtocol

from .forwarder import N8NForwarder

logger = logging.getLogger(__name__)


class BinanceBridge:
    def __init__(self, stream_url: str, forwarder: N8NForwarder) -> None:
        self.stream_url = stream_url
        self.forwarder = forwarder
        self.running = False
        self.last_message_at: datetime | None = None

    async def _handle_socket(self, websocket: WebSocketClientProtocol) -> None:
        async for raw in websocket:
            message = json.loads(raw)
            payload = {
                "source": "binance_ws",
                "stream": self.stream_url,
                "received_at": datetime.now(timezone.utc).isoformat(),
                "data": message,
            }
            await self.forwarder.forward(payload)
            self.last_message_at = datetime.now(timezone.utc)

    async def run(self) -> None:
        self.running = True
        backoff_seconds = 1
        while self.running:
            try:
                logger.info("Connecting Binance stream: %s", self.stream_url)
                async with websockets.connect(self.stream_url, ping_interval=20, ping_timeout=20) as ws:
                    backoff_seconds = 1
                    await self._handle_socket(ws)
            except Exception as exc:  # intentional broad catch for robust reconnect loop
                logger.warning("Bridge websocket error: %s", exc)
                await asyncio.sleep(backoff_seconds)
                backoff_seconds = min(backoff_seconds * 2, 30)

    def stop(self) -> None:
        self.running = False
