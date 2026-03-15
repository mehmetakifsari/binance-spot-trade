from __future__ import annotations

import httpx


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str) -> None:
        self.token = token
        self.chat_id = chat_id

    async def send(self, text: str) -> None:
        if not self.token or not self.chat_id:
            return
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(url, json={"chat_id": self.chat_id, "text": text})

    async def send_trade(self, side: str, symbol: str, qty: float, price: float, reason: str) -> None:
        await self.send(f"[PAPER {side}] {symbol} qty={qty:.6f} price={price:.4f}\nReason: {reason}")

    async def send_error(self, message: str) -> None:
        await self.send(f"[ERROR] {message}")

    async def send_summary(self, period: str, summary_text: str) -> None:
        await self.send(f"[{period.upper()} SUMMARY]\n{summary_text}")
