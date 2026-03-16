from fastapi.testclient import TestClient

from app import main


client = TestClient(main.app)


def test_n8n_page_requires_admin(monkeypatch):
    monkeypatch.setattr(main, "_is_admin", lambda request: False)

    response = client.get("/n8n-workflow", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/login"


def test_n8n_coin_list_requires_admin(monkeypatch):
    monkeypatch.setattr(main, "_is_admin", lambda request: False)

    response = client.get("/api/admin/n8n/coin-list")

    assert response.status_code == 403


def test_n8n_coin_list_returns_selected_symbols(monkeypatch):
    monkeypatch.setattr(main, "_is_admin", lambda request: True)
    monkeypatch.setattr(main, "_load_n8n_selected_symbols", lambda: ["BTCUSDT", "ETHUSDT"])

    response = client.get("/api/admin/n8n/coin-list")

    assert response.status_code == 200
    assert response.json()["selected_symbols"] == ["BTCUSDT", "ETHUSDT"]


def test_update_n8n_coin_list(monkeypatch):
    monkeypatch.setattr(main, "_is_admin", lambda request: True)
    monkeypatch.setattr(main, "_save_n8n_selected_symbols", lambda symbols: ["BTCUSDT"])

    response = client.post("/api/admin/n8n/coin-list", json={"symbols": ["btcusdt", "unknown"]})

    assert response.status_code == 200
    data = response.json()
    assert data["workflow_payload"]["name"] == "VisuTrade_Final_v2"
    fetch_binance_node = next(node for node in data["workflow_payload"]["nodes"] if node["name"] == "Fetch Binance")
    assert "symbol=BTCUSDT" in fetch_binance_node["parameters"]["url"]


def test_public_n8n_coin_list(monkeypatch):
    monkeypatch.setattr(main, "_load_n8n_selected_symbols", lambda: ["BTCUSDT", "SOLUSDT"])

    response = client.get("/api/n8n/coin-list")

    assert response.status_code == 200
    assert response.json()["count"] == 2
