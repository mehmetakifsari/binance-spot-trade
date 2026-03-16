from fastapi.testclient import TestClient

from app import main


client = TestClient(main.app)


def test_build_spec_signal_from_klines_returns_expected_fields():
    rows = [[0, "0", "0", "0", "100"], [0, "0", "0", "0", "101"], [0, "0", "0", "0", "102"]]

    signal = main._build_spec_signal_from_klines("BTCUSDT", rows)

    assert signal["symbol"] == "BTCUSDT"
    assert signal["status"] == "ok"
    assert signal["latest_price"] == 102.0
    assert "rsi" in signal
    assert "is_bearish" in signal
    assert "is_bullish" in signal
    assert "panic_score" in signal
    assert signal["signal_side"] in {"BULLISH", "BEARISH", "NEUTRAL"}


def test_coin_analysis_endpoint_requires_admin(monkeypatch):
    monkeypatch.setattr(main, "_is_admin", lambda request: False)

    response = client.get("/api/admin/coin-list/analysis")

    assert response.status_code == 403


def test_coin_analysis_endpoint_returns_analysis(monkeypatch):
    monkeypatch.setattr(main, "_is_admin", lambda request: True)
    monkeypatch.setattr(
        main,
        "_load_daily_coin_data",
        lambda day_key=None: {
            "day": "2026-01-01",
            "data": {
                "BTCUSDT": [[0, "0", "0", "0", "100"], [0, "0", "0", "0", "110"]],
                "ETHUSDT": [[0, "0", "0", "0", "200"], [0, "0", "0", "0", "190"]],
            },
        },
    )

    response = client.get("/api/admin/coin-list/analysis")

    assert response.status_code == 200
    payload = response.json()
    assert payload["day"] == "2026-01-01"
    assert payload["count"] == 2
    assert len(payload["analyses"]) == 2
