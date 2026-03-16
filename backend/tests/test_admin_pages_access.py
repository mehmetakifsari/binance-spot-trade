from fastapi.testclient import TestClient

from app import main


client = TestClient(main.app)


def test_trades_page_requires_admin(monkeypatch):
    monkeypatch.setattr(main, "_is_admin", lambda request: False)

    response = client.get("/trades", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/login"


def test_reports_page_requires_admin(monkeypatch):
    monkeypatch.setattr(main, "_is_admin", lambda request: False)

    response = client.get("/reports", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/login"


def test_state_monitor_page_requires_admin(monkeypatch):
    monkeypatch.setattr(main, "_is_admin", lambda request: False)

    response = client.get("/state-monitor", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/login"
