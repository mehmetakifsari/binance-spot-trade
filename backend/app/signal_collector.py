from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable

import httpx

logger = logging.getLogger(__name__)


@dataclass
class CollectorConfig:
    symbol: str = "BTCUSDT"
    interval: str = "15m"
    limit: int = 200
    period: int = 14
    loop_seconds: int = 60
    base_url: str = "https://api.binance.com"


def compute_rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) <= period:
        return 50.0

    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(deltas)):
        avg_gain = ((avg_gain * (period - 1)) + gains[i]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[i]) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


class SignalCollector:
    def __init__(self, config: CollectorConfig, on_signal: Callable[[dict], Awaitable[None]]):
        self.config = config
        self.on_signal = on_signal
        self.running = False
        self.last_run_at: datetime | None = None
        self.last_error: str | None = None

    async def _fetch_klines(self) -> list[list]:
        params = {
            "symbol": self.config.symbol,
            "interval": self.config.interval,
            "limit": self.config.limit,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{self.config.base_url}/api/v3/klines", params=params)
            resp.raise_for_status()
            payload = resp.json()
            if not isinstance(payload, list):
                raise ValueError("Unexpected klines payload")
            return payload

    def _build_signal(self, rows: list[list]) -> dict:
        closes = [float(r[4]) for r in rows if isinstance(r, list) and len(r) > 4]
        if not closes:
            raise ValueError("No close price in klines response")

        price = closes[-1]
        rsi = compute_rsi(closes, self.config.period)

        return {
            "symbol": self.config.symbol,
            "price": price,
            "rsi": rsi,
            "is_bearish": rsi >= 70,
            "is_bullish": rsi <= 30,
            "panic_score": 1.0 if rsi >= 80 else 0.0,
        }

    async def run_once(self) -> None:
        rows = await self._fetch_klines()
        signal = self._build_signal(rows)
        await self.on_signal(signal)
        self.last_run_at = datetime.now(timezone.utc)
        self.last_error = None

    async def run_forever(self) -> None:
        self.running = True
        logger.info("Signal collector started for %s", self.config.symbol)
        try:
            while self.running:
                try:
                    await self.run_once()
                except Exception as exc:
                    self.last_error = str(exc)
                    logger.warning("Signal collector loop failed: %s", exc)
                await asyncio.sleep(self.config.loop_seconds)
        finally:
            self.running = False

    def stop(self) -> None:
        self.running = False
