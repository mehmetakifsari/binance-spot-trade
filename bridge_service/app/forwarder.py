from __future__ import annotations

import httpx


class N8NForwarder:
    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url
        self.client = httpx.AsyncClient(timeout=10)

    async def forward(self, payload: dict) -> None:
        response = await self.client.post(self.webhook_url, json=payload)
        response.raise_for_status()

    async def close(self) -> None:
        await self.client.aclose()
