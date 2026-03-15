from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text

from .config import settings
from .db import SessionLocal
from .paper_trading import BalanceState, execute_buy, execute_sell
from .reporting import format_summary
from .state_machine import BotState, RuntimeState, SignalInput, evaluate_signal
from .telegram import TelegramNotifier

app = FastAPI(title="VisuTrade Backend + Dashboard")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")
notifier = TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id)


class SignalPayload(BaseModel):
    symbol: str = "BTCUSDT"
    price: float
    rsi: float
    is_bearish: bool = False
    is_bullish: bool = False
    panic_score: float = 0.0


def _fetch_or_init_state(db, symbol: str) -> dict:
    state_row = db.execute(text("SELECT * FROM bot_state WHERE symbol=:symbol"), {"symbol": symbol}).mappings().first()
    if state_row:
        return dict(state_row)

    db.execute(
        text(
            """
            INSERT INTO bot_state(symbol, state, drop_blocks, rise_blocks, bearish_moves, bullish_moves, panic_mode, cash_usdt, asset_qty, latest_price, latest_rsi)
            VALUES(:symbol, :state, 0, 0, 0, 0, false, :cash, 0, 0, 0)
            """
        ),
        {"symbol": symbol, "state": BotState.NEUTRAL.value, "cash": settings.starting_balance_usdt},
    )
    db.commit()
    return _fetch_or_init_state(db, symbol)


def _update_position_snapshot(db, symbol: str, price: float, cash: float, asset_qty: float) -> None:
    current_value = asset_qty * price
    if asset_qty > 0:
        existing_open = db.execute(
            text("SELECT id FROM positions WHERE symbol=:symbol AND status='OPEN' LIMIT 1"),
            {"symbol": symbol},
        ).scalar()
        if existing_open:
            db.execute(
                text(
                    """
                    UPDATE positions
                    SET qty=:qty, current_value_usdt=:value, updated_at=now()
                    WHERE id=:id
                    """
                ),
                {"id": existing_open, "qty": asset_qty, "value": current_value},
            )
        else:
            db.execute(
                text(
                    """
                    INSERT INTO positions(symbol, status, qty, current_value_usdt, opened_at, updated_at)
                    VALUES(:symbol, 'OPEN', :qty, :value, now(), now())
                    """
                ),
                {"symbol": symbol, "qty": asset_qty, "value": current_value},
            )
    else:
        db.execute(
            text(
                """
                UPDATE positions
                SET status='CLOSED', qty=0, current_value_usdt=0, closed_at=now(), updated_at=now()
                WHERE symbol=:symbol AND status='OPEN'
                """
            ),
            {"symbol": symbol},
        )


@app.get("/health")
@app.get("/api/health")
async def health() -> dict:
    return {
        "status": "ok",
        "env": settings.app_env,
        "frontend_base_url": settings.frontend_base_url,
        "backend_base_url": settings.backend_base_url,
    }


@app.post("/signals")
@app.post("/api/signals")
async def process_signal(payload: SignalPayload) -> dict:
    db = SessionLocal()
    try:
        state = _fetch_or_init_state(db, payload.symbol)
        runtime = RuntimeState(
            state=BotState(state["state"]),
            drop_blocks=state["drop_blocks"],
            rise_blocks=state["rise_blocks"],
            bearish_moves=state["bearish_moves"],
            bullish_moves=state["bullish_moves"],
            panic_mode=state["panic_mode"],
            cooldown_until=state["cooldown_until"],
            last_rsi=state["latest_rsi"],
        )
        signal = SignalInput(**payload.model_dump())
        decision = evaluate_signal(runtime, signal, settings.trade_cooldown_seconds)

        balance = BalanceState(cash_usdt=float(state["cash_usdt"]), asset_qty=float(state["asset_qty"]))
        trade_result = None

        if decision.action == "BUY":
            buy_notional = settings.panic_buy_usdt if decision.panic_mode else settings.normal_buy_usdt
            balance, qty = execute_buy(balance, payload.price, buy_notional)
            trade_result = {"side": "BUY", "qty": qty, "notional": buy_notional}
            await notifier.send_trade("BUY", payload.symbol, qty, payload.price, decision.reason)
        elif decision.action == "SELL":
            if balance.asset_qty > 0:
                balance, qty, proceeds = execute_sell(balance, payload.price)
                trade_result = {"side": "SELL", "qty": qty, "notional": proceeds}
                await notifier.send_trade("SELL", payload.symbol, qty, payload.price, decision.reason)
            else:
                decision.action = "HOLD"
                decision.reason = "Sell signal ignored: no active position"

        db.execute(
            text(
                """
                UPDATE bot_state
                SET state=:state, drop_blocks=:drop_blocks, rise_blocks=:rise_blocks,
                    bearish_moves=:bearish_moves, bullish_moves=:bullish_moves,
                    panic_mode=:panic_mode, cooldown_until=:cooldown_until,
                    latest_price=:price, latest_rsi=:rsi, cash_usdt=:cash, asset_qty=:asset,
                    updated_at=now()
                WHERE symbol=:symbol
                """
            ),
            {
                "state": decision.new_state.value,
                "drop_blocks": runtime.drop_blocks,
                "rise_blocks": runtime.rise_blocks,
                "bearish_moves": runtime.bearish_moves,
                "bullish_moves": runtime.bullish_moves,
                "panic_mode": runtime.panic_mode,
                "cooldown_until": runtime.cooldown_until,
                "price": payload.price,
                "rsi": payload.rsi,
                "cash": balance.cash_usdt,
                "asset": balance.asset_qty,
                "symbol": payload.symbol,
            },
        )

        if trade_result:
            db.execute(
                text(
                    """
                    INSERT INTO trades(symbol, side, qty, price, notional_usdt, reason, signal_snapshot, created_at)
                    VALUES(:symbol, :side, :qty, :price, :notional, :reason, :snapshot::jsonb, now())
                    """
                ),
                {
                    "symbol": payload.symbol,
                    "side": trade_result["side"],
                    "qty": trade_result["qty"],
                    "price": payload.price,
                    "notional": trade_result["notional"],
                    "reason": decision.reason,
                    "snapshot": payload.model_dump_json(),
                },
            )

        equity = balance.cash_usdt + (balance.asset_qty * payload.price)
        db.execute(
            text(
                """
                INSERT INTO balance_snapshots(symbol, cash_usdt, asset_qty, mark_price, equity_usdt, snapshot_time)
                VALUES(:symbol, :cash, :asset, :price, :equity, now())
                """
            ),
            {"symbol": payload.symbol, "cash": balance.cash_usdt, "asset": balance.asset_qty, "price": payload.price, "equity": equity},
        )
        _update_position_snapshot(db, payload.symbol, payload.price, balance.cash_usdt, balance.asset_qty)
        db.commit()

        return {"action": decision.action, "reason": decision.reason, "state": decision.new_state.value, "equity": equity}
    except Exception as exc:
        db.rollback()
        await notifier.send_error(str(exc))
        raise
    finally:
        db.close()


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    db = SessionLocal()
    try:
        row = db.execute(text("SELECT * FROM bot_state ORDER BY updated_at DESC LIMIT 1")).mappings().first()
        latest = db.execute(text("SELECT * FROM balance_snapshots ORDER BY snapshot_time DESC LIMIT 1")).mappings().first()
    except SQLAlchemyError:
        row = None
        latest = None
    finally:
        db.close()
    equity = float(latest["equity_usdt"]) if latest else settings.starting_balance_usdt
    active_qty = float(row["asset_qty"]) if row else 0.0
    mark_price = float(row["latest_price"]) if row else 0.0
    cost_basis = settings.starting_balance_usdt - (float(row["cash_usdt"]) if row else settings.starting_balance_usdt)
    unrealized_pnl = (active_qty * mark_price) - max(cost_basis, 0)
    realized_pnl = equity - settings.starting_balance_usdt - unrealized_pnl
    context = {
        "request": request,
        "state": row,
        "start_balance": settings.starting_balance_usdt,
        "equity": equity,
        "realized_pnl": realized_pnl,
        "unrealized_pnl": unrealized_pnl,
    }
    return templates.TemplateResponse("dashboard.html", context)


@app.get("/trades", response_class=HTMLResponse)
async def trades_page(request: Request):
    db = SessionLocal()
    try:
        trades = db.execute(text("SELECT * FROM trades ORDER BY created_at DESC LIMIT 200")).mappings().all()
    except SQLAlchemyError:
        trades = []
    finally:
        db.close()
    return templates.TemplateResponse("trades.html", {"request": request, "trades": trades})


@app.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request):
    db = SessionLocal()
    try:
        latest = db.execute(text("SELECT * FROM balance_snapshots ORDER BY snapshot_time DESC LIMIT 1")).mappings().first()
    except SQLAlchemyError:
        latest = None
    finally:
        db.close()
    equity = float(latest["equity_usdt"]) if latest else settings.starting_balance_usdt
    summary = format_summary(settings.starting_balance_usdt, equity, equity - settings.starting_balance_usdt, 0.0)
    return templates.TemplateResponse("reports.html", {"request": request, "summary": summary})


@app.get("/state-monitor", response_class=HTMLResponse)
async def state_monitor(request: Request):
    db = SessionLocal()
    try:
        states = db.execute(text("SELECT symbol, state, latest_rsi, drop_blocks, rise_blocks, cooldown_until, panic_mode FROM bot_state ORDER BY symbol")).mappings().all()
    except SQLAlchemyError:
        states = []
    finally:
        db.close()
    return templates.TemplateResponse("state_monitor.html", {"request": request, "states": states, "now": datetime.now(timezone.utc)})
