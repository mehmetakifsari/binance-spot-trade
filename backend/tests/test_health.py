from fastapi import HTTPException

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
