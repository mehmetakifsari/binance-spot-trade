from datetime import datetime, timezone, timedelta

from app.state_machine import BotState, RuntimeState, SignalInput, evaluate_signal


def test_buy_after_drop_block_and_rebound_confirmation():
    runtime = RuntimeState(
        state=BotState.WATCH_DROP,
        drop_blocks=1,
        rise_blocks=0,
        bearish_moves=0,
        bullish_moves=1,
        last_rsi=30,
    )
    signal = SignalInput(symbol="BTCUSDT", price=100.0, rsi=35.0, is_bearish=False, is_bullish=True)

    decision = evaluate_signal(runtime, signal, cooldown_seconds=60)

    assert decision.action == "BUY"
    assert decision.new_state == BotState.BOUGHT
    assert runtime.cooldown_until is not None


def test_sell_after_three_rise_blocks():
    runtime = RuntimeState(state=BotState.WATCH_RISE, rise_blocks=3, drop_blocks=1, last_rsi=55)
    signal = SignalInput(symbol="BTCUSDT", price=110.0, rsi=57.0, is_bearish=False, is_bullish=False)

    decision = evaluate_signal(runtime, signal, cooldown_seconds=60)

    assert decision.action == "SELL"
    assert decision.new_state == BotState.SOLD
    assert runtime.rise_blocks == 0


def test_cooldown_blocks_actions_until_expired():
    runtime = RuntimeState(state=BotState.BOUGHT, cooldown_until=datetime.now(timezone.utc) + timedelta(seconds=30), last_rsi=50)
    signal = SignalInput(symbol="BTCUSDT", price=100.0, rsi=51.0, is_bearish=False, is_bullish=True)

    decision = evaluate_signal(runtime, signal, cooldown_seconds=60)

    assert decision.action == "HOLD"
    assert decision.new_state == BotState.COOLDOWN
