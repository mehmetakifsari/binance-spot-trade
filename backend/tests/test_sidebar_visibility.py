from fastapi.testclient import TestClient

from app import main


client = TestClient(main.app)


def test_sidebar_hides_admin_sections_for_non_admin(monkeypatch):
    monkeypatch.setattr(main, "_is_admin", lambda request: False)

    response = client.get("/")

    assert response.status_code == 200
    assert '/login">Admin Girişi</a>' in response.text
    assert '/trades">Trades</a>' not in response.text
    assert '/reports">Reports</a>' not in response.text
    assert '/state-monitor">State Monitor</a>' not in response.text
    assert '/coin-list">Coin Listesi</a>' not in response.text


def test_sidebar_shows_admin_sections_for_admin(monkeypatch):
    monkeypatch.setattr(main, "_is_admin", lambda request: True)

    response = client.get("/")

    assert response.status_code == 200
    assert '/dashboard">Dashboard</a>' in response.text
    assert '/trades">Trades</a>' in response.text
    assert '/reports">Reports</a>' in response.text
    assert '/state-monitor">State Monitor</a>' in response.text
    assert '/coin-list">Coin Listesi</a>' in response.text
