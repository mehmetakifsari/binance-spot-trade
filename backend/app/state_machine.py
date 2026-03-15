from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from enum import Enum


class BotState(str, Enum):
    NEUTRAL = "NEUTRAL"
    WATCH_DROP = "WATCH_DROP"
    WAIT_CONFIRM = "WAIT_CONFIRM"
    BUY_READY = "BUY_READY"
    BOUGHT = "BOUGHT"
    PANIC_WAIT = "PANIC_WAIT"
    PANIC_BOUGHT = "PANIC_BOUGHT"
    WATCH_RISE = "WATCH_RISE"
    SOLD = "SOLD"
    COOLDOWN = "COOLDOWN"


@dataclass
class SignalInput:
    symbol: str
    price: float
    rsi: float
    is_bearish: bool
    is_bullish: bool
    panic_score: float = 0.0


@dataclass
class RuntimeState:
    state: BotState = BotState.NEUTRAL
    drop_blocks: int = 0
    rise_blocks: int = 0
    bearish_moves: int = 0
    bullish_moves: int = 0
    panic_mode: bool = False
    cooldown_until: datetime | None = None
    last_rsi: float | None = None


@dataclass
class Decision:
    action: str = "HOLD"  # HOLD|BUY|SELL
    new_state: BotState = BotState.NEUTRAL
    reason: str = "No action"
    panic_mode: bool = False


def evaluate_signal(runtime: RuntimeState, signal: SignalInput, cooldown_seconds: int) -> Decision:
    now = datetime.now(timezone.utc)

    if runtime.cooldown_until and now < runtime.cooldown_until:
        runtime.state = BotState.COOLDOWN
        return Decision(action="HOLD", new_state=runtime.state, reason="Cooldown active", panic_mode=runtime.panic_mode)

    if runtime.state == BotState.COOLDOWN and runtime.cooldown_until and now >= runtime.cooldown_until:
        runtime.state = BotState.NEUTRAL
        runtime.cooldown_until = None

    if signal.is_bearish:
        runtime.bearish_moves += 1
        if runtime.bearish_moves >= 2:
            runtime.drop_blocks += 1
            runtime.bearish_moves = 0
            runtime.state = BotState.WATCH_DROP

    if signal.is_bullish:
        runtime.bullish_moves += 1
        if runtime.bullish_moves >= 2:
            runtime.rise_blocks += 1
            runtime.bullish_moves = 0
            runtime.state = BotState.WATCH_RISE

    rsi_turn_up = runtime.last_rsi is not None and signal.rsi > runtime.last_rsi
    runtime.last_rsi = signal.rsi

    if signal.panic_score >= 8.0:
        runtime.panic_mode = True
        runtime.state = BotState.PANIC_WAIT
        if rsi_turn_up and signal.rsi >= 30:
            runtime.cooldown_until = now + timedelta(seconds=cooldown_seconds)
            runtime.state = BotState.PANIC_BOUGHT
            return Decision(action="BUY", new_state=runtime.state, reason="Panic rebound buy", panic_mode=True)
        return Decision(action="HOLD", new_state=runtime.state, reason="Panic wait for confirmation", panic_mode=True)

    if runtime.drop_blocks >= 1 and rsi_turn_up and signal.is_bullish:
        runtime.state = BotState.BOUGHT
        runtime.panic_mode = False
        runtime.cooldown_until = now + timedelta(seconds=cooldown_seconds)
        runtime.rise_blocks = 0
        return Decision(action="BUY", new_state=runtime.state, reason="Drop block + rebound confirmation", panic_mode=False)

    if runtime.rise_blocks >= 3:
        runtime.state = BotState.SOLD
        runtime.cooldown_until = now + timedelta(seconds=cooldown_seconds)
        runtime.drop_blocks = 0
        runtime.rise_blocks = 0
        runtime.panic_mode = False
        return Decision(action="SELL", new_state=runtime.state, reason="Safe sell after 3 rise blocks", panic_mode=False)

    if runtime.rise_blocks >= 1 and signal.rsi > 75 and signal.is_bearish:
        runtime.state = BotState.SOLD
        runtime.cooldown_until = now + timedelta(seconds=cooldown_seconds)
        runtime.rise_blocks = 0
        runtime.panic_mode = False
        return Decision(action="SELL", new_state=runtime.state, reason="Defensive exhaustion sell", panic_mode=False)

    return Decision(action="HOLD", new_state=runtime.state, reason="Conditions not met", panic_mode=runtime.panic_mode)
