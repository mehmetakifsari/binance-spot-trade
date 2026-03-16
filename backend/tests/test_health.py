from fastapi import HTTPException
from starlette.requests import Request

from app import main
from app.main import _effective_base_url, _is_localhost_url, _parse_signal_payload


def test_is_localhost_url_detects_local_addresses():
    assert _is_localhost_url("http://localhost:8000")
    assert _is_localhost_url("https://127.0.0.1:9000")


def test_effective_base_url_uses_request_for_local_defaults():
    request_base_url = "https://api-trade.visupanel.com"
    assert _effective_base_url("http://localhost:8000", request_base_url) == request_base_url
    assert _effective_base_url("https://127.0.0.1:8000", request_base_url) == request_base_url


def test_effective_base_url_preserves_configured_public_url():
    request_base_url = "https://api-trade.visupanel.com"
    configured = "https://trade.visupanel.com"
    assert _effective_base_url(configured, request_base_url) == configured


def test_parse_signal_payload_accepts_single_item_array():
    payload = _parse_signal_payload(
        [
            {
                "symbol": "BTCUSDT",
                "price": 72021.01,
                "rsi": 65.19,
                "is_bearish": False,
                "is_bullish": True,
                "panic_score": 0,
            }
        ]
    )

    assert payload.symbol == "BTCUSDT"
    assert payload.price == 72021.01


def test_parse_signal_payload_rejects_multi_item_array():
    try:
        _parse_signal_payload([{"symbol": "BTCUSDT", "price": 1, "rsi": 50}, {"symbol": "ETHUSDT", "price": 2, "rsi": 40}])
    except HTTPException as exc:
        assert exc.status_code == 422
        assert "exactly one" in str(exc.detail)
    else:
        raise AssertionError("Expected HTTPException for invalid signal array")


def test_upsert_admin_user_handles_mongo_failures(monkeypatch):
    def fail_sync():
        raise RuntimeError("mongo down")

    monkeypatch.setattr(main, "_sync_admin_hash_mongodb", fail_sync)
    main._upsert_admin_user()


def test_login_fallback_accepts_default_admin_when_mongo_unavailable(monkeypatch):
    async def _receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/login",
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
        },
        receive=_receive,
    )

    def fail_mongo():
        raise RuntimeError("mongo down")

    monkeypatch.setattr(main, "_mongo_collection", fail_mongo)
    main.fallback_admin_sessions.clear()

    import asyncio

    response = asyncio.run(main.login_submit(request, main.DEFAULT_ADMIN_USERNAME, main.DEFAULT_ADMIN_PASSWORD))

    assert response.status_code == 302
    set_cookie = response.headers.get("set-cookie", "")
    assert "admin_session=" in set_cookie


def test_is_admin_uses_fallback_session_when_mongo_unavailable(monkeypatch):
    token = "fallback-token"
    signed = main._build_session_cookie_value(token)
    main.fallback_admin_sessions.clear()
    main.fallback_admin_sessions.add(token)

    async def _receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/dashboard",
            "headers": [(b"cookie", f"admin_session={signed}".encode("utf-8"))],
            "query_string": b"",
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
        },
        receive=_receive,
    )

    def fail_mongo():
        raise RuntimeError("mongo down")

    monkeypatch.setattr(main, "_mongo_collection", fail_mongo)

    assert main._is_admin(request)
