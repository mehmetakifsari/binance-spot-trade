import asyncio

from app.main import _safe_notify


async def _ok_call() -> None:
    return None


async def _failing_call() -> None:
    raise RuntimeError("telegram unavailable")


def test_safe_notify_allows_successful_notification() -> None:
    asyncio.run(_safe_notify("ok", _ok_call()))


def test_safe_notify_swallows_notification_errors() -> None:
    asyncio.run(_safe_notify("error", _failing_call()))
