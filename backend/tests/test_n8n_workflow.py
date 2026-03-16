from fastapi.testclient import TestClient

from app import main


client = TestClient(main.app)


def test_coin_list_page_requires_admin(monkeypatch):
    monkeypatch.setattr(main, "_is_admin", lambda request: False)

    response = client.get("/coin-list", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/login"


def test_coin_list_requires_admin(monkeypatch):
    monkeypatch.setattr(main, "_is_admin", lambda request: False)

    response = client.get("/api/admin/coin-list")

    assert response.status_code == 403


def test_coin_list_returns_selected_symbols(monkeypatch):
    monkeypatch.setattr(main, "_is_admin", lambda request: True)
    monkeypatch.setattr(main, "_load_selected_symbols", lambda: ["BTCUSDT", "ETHUSDT"])
    async def fake_symbols():
        return ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

    monkeypatch.setattr(main, "_fetch_binance_exchange_symbols", fake_symbols)

    response = client.get("/api/admin/coin-list")

    assert response.status_code == 200
    assert response.json()["selected_symbols"] == ["BTCUSDT", "ETHUSDT"]


def test_update_coin_list(monkeypatch):
    monkeypatch.setattr(main, "_is_admin", lambda request: True)
    monkeypatch.setattr(main, "_save_selected_symbols", lambda symbols: ["BTCUSDT"])

    response = client.post("/api/admin/coin-list", json={"symbols": ["btcusdt", "unknown"]})

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["selected_symbols"] == ["BTCUSDT"]


def test_public_coin_list(monkeypatch):
    monkeypatch.setattr(main, "_load_selected_symbols", lambda: ["BTCUSDT", "SOLUSDT"])

    response = client.get("/api/coin-list")

    assert response.status_code == 200
    assert response.json()["count"] == 2


def test_coin_list_filters_removed_symbols(monkeypatch):
    monkeypatch.setattr(main, "_is_admin", lambda request: True)
    monkeypatch.setattr(main, "_load_selected_symbols", lambda: ["BTCUSDT", "DELISTUSDT"])
    monkeypatch.setattr(main, "_save_selected_symbols", lambda symbols: symbols)

    async def fake_symbols(force_refresh: bool = False):
        assert force_refresh is False
        return ["BTCUSDT", "ETHUSDT"]

    monkeypatch.setattr(main, "_fetch_binance_exchange_symbols", fake_symbols)

    response = client.get("/api/admin/coin-list")

    assert response.status_code == 200
    data = response.json()
    assert data["selected_symbols"] == ["BTCUSDT"]
    assert data["removed_symbols"] == ["DELISTUSDT"]


def test_sync_coin_list_endpoint(monkeypatch):
    monkeypatch.setattr(main, "_is_admin", lambda request: True)
    monkeypatch.setattr(main, "_invalidate_binance_symbols_cache", lambda: None)
    monkeypatch.setattr(main, "_load_selected_symbols", lambda: ["BTCUSDT", "OLDUSDT"])
    monkeypatch.setattr(main, "_save_selected_symbols", lambda symbols: symbols)

    async def fake_symbols(force_refresh: bool = False):
        assert force_refresh is True
        return ["BTCUSDT", "SOLUSDT"]

    monkeypatch.setattr(main, "_fetch_binance_exchange_symbols", fake_symbols)

    response = client.post("/api/admin/coin-list/sync")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["selected_symbols"] == ["BTCUSDT"]
    assert data["removed_symbols"] == ["OLDUSDT"]
