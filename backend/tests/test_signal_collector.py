from app.signal_collector import CollectorConfig, SignalCollector, compute_rsi


def test_compute_rsi_returns_neutral_when_not_enough_data():
    assert compute_rsi([1, 2, 3], period=14) == 50.0


def test_compute_rsi_reaches_upper_bound_on_monotonic_gain():
    closes = [float(v) for v in range(1, 40)]
    assert compute_rsi(closes, period=14) == 100.0


def test_build_signal_generates_expected_fields():
    collector = SignalCollector(CollectorConfig(symbol="BTCUSDT"), on_signal=lambda payload: None)
    rows = [[0, "0", "0", "0", "100"], [0, "0", "0", "0", "101"], [0, "0", "0", "0", "102"]]
    signal = collector._build_signal(rows)

    assert signal["symbol"] == "BTCUSDT"
    assert signal["price"] == 102.0
    assert "rsi" in signal
    assert "is_bearish" in signal
    assert "is_bullish" in signal
    assert "panic_score" in signal
