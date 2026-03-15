from app.main import _effective_base_url, _is_localhost_url


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
