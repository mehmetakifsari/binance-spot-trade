from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import os
import secrets
from typing import Awaitable, Any

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
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
from .signal_collector import CollectorConfig, SignalCollector

@asynccontextmanager
async def lifespan(app: FastAPI):
    global collector, collector_task, admin_hash_sync_task
    _upsert_admin_user()
    admin_hash_sync_task = asyncio.create_task(_admin_hash_sync_loop())
    if settings.signal_collector_enabled:
        collector = SignalCollector(
            CollectorConfig(
                symbol=settings.signal_collector_symbol,
                interval=settings.signal_collector_interval,
                limit=settings.signal_collector_limit,
                period=settings.signal_collector_period,
                loop_seconds=settings.signal_collector_loop_seconds,
            ),
            on_signal=lambda payload: _process_signal(SignalPayload.model_validate(payload)),
        )
        collector_task = asyncio.create_task(collector.run_forever())
        logger.info("Signal collector enabled for %s", settings.signal_collector_symbol)
    try:
        yield
    finally:
        if collector:
            collector.stop()
        if collector_task:
            collector_task.cancel()
        if admin_hash_sync_task:
            admin_hash_sync_task.cancel()


app = FastAPI(title="VisuTrade Backend + Dashboard", lifespan=lifespan)
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
logger = logging.getLogger(__name__)
collector: SignalCollector | None = None
collector_task: asyncio.Task | None = None
admin_hash_sync_task: asyncio.Task | None = None
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "Atmaca@53"
SESSION_SIGNING_PEPPER = "visutrade-session-pepper-v1"
fallback_admin_sessions: set[str] = set()


def _hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return f"pbkdf2_sha256$120000${salt.hex()}${digest.hex()}"


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = password_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        new_digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        ).hex()
        return hmac.compare_digest(new_digest, digest_hex)
    except (ValueError, TypeError):
        return False


def _session_signature(token: str) -> str:
    payload = f"{token}:{SESSION_SIGNING_PEPPER}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _build_session_cookie_value(token: str) -> str:
    return f"{token}.{_session_signature(token)}"


def _parse_session_cookie(raw_cookie: str) -> str | None:
    if not raw_cookie or "." not in raw_cookie:
        return None
    token, signature = raw_cookie.split(".", 1)
    if not token or not hmac.compare_digest(signature, _session_signature(token)):
        return None
    return token


def _mongo_collection():
    from pymongo import MongoClient

    client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=2000)
    return client[settings.mongodb_auth_db][settings.mongodb_auth_collection]


def _sync_admin_hash_mongodb() -> None:
    collection = _mongo_collection()
    existing = collection.find_one({"username": DEFAULT_ADMIN_USERNAME})
    if existing and _verify_password(DEFAULT_ADMIN_PASSWORD, existing.get("password_hash", "")):
        return

    password_hash = _hash_password(DEFAULT_ADMIN_PASSWORD)
    now = datetime.now(timezone.utc)
    collection.update_one(
        {"username": DEFAULT_ADMIN_USERNAME},
        {
            "$set": {"password_hash": password_hash, "updated_at": now},
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )


def _sync_admin_session(token: str) -> None:
    collection = _mongo_collection()
    now = datetime.now(timezone.utc)
    collection.update_one(
        {"username": DEFAULT_ADMIN_USERNAME},
        {
            "$set": {"session_token": token, "session_updated_at": now},
        },
    )


def _clear_admin_session(token: str | None = None) -> None:
    collection = _mongo_collection()
    query = {"username": DEFAULT_ADMIN_USERNAME}
    if token:
        query["session_token"] = token
    collection.update_one(query, {"$unset": {"session_token": "", "session_updated_at": ""}})


def _is_admin(request: Request) -> bool:
    raw_cookie = request.cookies.get("admin_session", "")
    token = _parse_session_cookie(raw_cookie)
    if not token:
        return False
    try:
        collection = _mongo_collection()
        row = collection.find_one({"username": DEFAULT_ADMIN_USERNAME, "session_token": token})
        if row:
            return True
    except Exception as exc:
        logger.warning("Mongo admin session check failed, using fallback session store: %s", exc)
    return token in fallback_admin_sessions


def _require_admin(request: Request) -> None:
    if not _is_admin(request):
        raise HTTPException(status_code=403, detail="Admin authorization required")


def _upsert_admin_user() -> None:
    try:
        _sync_admin_hash_mongodb()
    except Exception as exc:
        logger.warning("Initial Mongo admin sync failed: %s", exc)


async def _admin_hash_sync_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(_sync_admin_hash_mongodb)
        except Exception as exc:
            logger.warning("Mongo admin hash sync failed: %s", exc)
        await asyncio.sleep(300)


async def _safe_notify(event: str, notify_call: Awaitable[None]) -> None:
    try:
        await notify_call
    except Exception as exc:
        logger.warning("Telegram notify failed for %s: %s", event, exc)


def _is_localhost_url(value: str) -> bool:
    normalized = value.lower()
    return "localhost" in normalized or "127.0.0.1" in normalized


def _effective_base_url(configured_base_url: str, request_base_url: str) -> str:
    if not configured_base_url or _is_localhost_url(configured_base_url):
        return request_base_url
    return configured_base_url


class SignalPayload(BaseModel):
    symbol: str = "BTCUSDT"
    price: float
    rsi: float
    is_bearish: bool = False
    is_bullish: bool = False
    panic_score: float = 0.0


def _parse_signal_payload(raw_payload: Any) -> SignalPayload:
    if isinstance(raw_payload, list):
        if len(raw_payload) != 1:
            raise HTTPException(
                status_code=422,
                detail="Signal payload array must contain exactly one item.",
            )
        raw_payload = raw_payload[0]

    if not isinstance(raw_payload, dict):
        raise HTTPException(status_code=422, detail="Signal payload must be a JSON object.")

    try:
        return SignalPayload.model_validate(raw_payload)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid signal payload: {exc}") from exc


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
async def health(request: Request) -> dict:
    request_base_url = str(request.base_url).rstrip("/")
    frontend_base_url = _effective_base_url(settings.frontend_base_url, request_base_url)
    backend_base_url = _effective_base_url(settings.backend_base_url, request_base_url)

    return {
        "status": "ok",
        "env": settings.app_env,
        "frontend_base_url": frontend_base_url,
        "backend_base_url": backend_base_url,
        "request_base_url": request_base_url,
        "uses_localhost_defaults": any(
            _is_localhost_url(value)
            for value in (settings.frontend_base_url, settings.backend_base_url)
        ),
    }


async def _process_signal(payload: SignalPayload) -> dict:
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
            await _safe_notify(
                "trade-buy",
                notifier.send_trade("BUY", payload.symbol, qty, payload.price, decision.reason),
            )
        elif decision.action == "SELL":
            if balance.asset_qty > 0:
                balance, qty, proceeds = execute_sell(balance, payload.price)
                trade_result = {"side": "SELL", "qty": qty, "notional": proceeds}
                await _safe_notify(
                    "trade-sell",
                    notifier.send_trade("SELL", payload.symbol, qty, payload.price, decision.reason),
                )
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
        await _safe_notify("process-signal-error", notifier.send_error(str(exc)))
        raise
    finally:
        db.close()




@app.post("/signals")
@app.post("/api/signals")
async def process_signal(request: Request) -> dict:
    payload = _parse_signal_payload(await request.json())
    return await _process_signal(payload)


@app.post("/api/admin/signal-collector/run-once")
async def run_signal_collector_once(request: Request) -> dict:
    _require_admin(request)
    global collector
    if not collector:
        collector = SignalCollector(
            CollectorConfig(
                symbol=settings.signal_collector_symbol,
                interval=settings.signal_collector_interval,
                limit=settings.signal_collector_limit,
                period=settings.signal_collector_period,
                loop_seconds=settings.signal_collector_loop_seconds,
            ),
            on_signal=lambda payload: _process_signal(SignalPayload.model_validate(payload)),
        )
    await collector.run_once()
    return {"status": "ok", "last_run_at": collector.last_run_at.isoformat() if collector.last_run_at else None}


@app.get("/api/admin/signal-collector")
async def signal_collector_status(request: Request) -> dict:
    _require_admin(request)
    return {
        "enabled": settings.signal_collector_enabled,
        "running": collector.running if collector else False,
        "symbol": settings.signal_collector_symbol,
        "interval": settings.signal_collector_interval,
        "loop_seconds": settings.signal_collector_loop_seconds,
        "last_run_at": collector.last_run_at.isoformat() if collector and collector.last_run_at else None,
        "last_error": collector.last_error if collector else None,
    }


@app.get("/signals")
@app.get("/api/signals")
async def signal_endpoint_help() -> dict:
    return {
        "detail": "Use POST /api/signals with JSON body.",
        "example": {
            "symbol": "BTCUSDT",
            "price": 72021.01,
            "rsi": 65.19,
            "is_bearish": False,
            "is_bullish": True,
            "panic_score": 0,
        },
    }


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "is_admin": _is_admin(request)})


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if _is_admin(request):
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    row = None
    try:
        collection = _mongo_collection()
        row = collection.find_one({"username": username})
    except Exception as exc:
        logger.warning("Mongo login lookup failed, falling back to env admin credentials: %s", exc)

    valid_credentials = bool(row and _verify_password(password, row.get("password_hash", "")))
    if not valid_credentials:
        valid_credentials = username == DEFAULT_ADMIN_USERNAME and password == DEFAULT_ADMIN_PASSWORD

    if not valid_credentials:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Kullanıcı adı veya şifre hatalı."},
            status_code=401,
        )

    session_token = secrets.token_urlsafe(32)
    try:
        _sync_admin_session(session_token)
    except Exception as exc:
        logger.warning("Mongo session sync failed, storing fallback admin session: %s", exc)
        fallback_admin_sessions.add(session_token)

    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie("admin_session", _build_session_cookie_value(session_token), httponly=True, samesite="lax")
    return response


@app.post("/logout")
async def logout(request: Request):
    raw_cookie = request.cookies.get("admin_session", "")
    token = _parse_session_cookie(raw_cookie)
    if token:
        fallback_admin_sessions.discard(token)
        try:
            _clear_admin_session(token)
        except Exception as exc:
            logger.warning("Mongo logout sync failed for admin session: %s", exc)

    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("admin_session")
    return response


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    if not _is_admin(request):
        return RedirectResponse(url="/login", status_code=302)

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
        "is_admin": _is_admin(request),
        "state": row,
        "start_balance": settings.starting_balance_usdt,
        "equity": equity,
        "realized_pnl": realized_pnl,
        "unrealized_pnl": unrealized_pnl,
    }
    return templates.TemplateResponse("dashboard.html", context)


@app.get("/trades", response_class=HTMLResponse)
async def trades_page(request: Request):
    if not _is_admin(request):
        return RedirectResponse(url="/login", status_code=302)

    db = SessionLocal()
    try:
        trades = db.execute(text("SELECT * FROM trades ORDER BY created_at DESC LIMIT 200")).mappings().all()
    except SQLAlchemyError:
        trades = []
    finally:
        db.close()
    return templates.TemplateResponse("trades.html", {"request": request, "trades": trades, "is_admin": _is_admin(request)})


@app.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request):
    if not _is_admin(request):
        return RedirectResponse(url="/login", status_code=302)

    db = SessionLocal()
    try:
        latest = db.execute(text("SELECT * FROM balance_snapshots ORDER BY snapshot_time DESC LIMIT 1")).mappings().first()
    except SQLAlchemyError:
        latest = None
    finally:
        db.close()
    equity = float(latest["equity_usdt"]) if latest else settings.starting_balance_usdt
    summary = format_summary(settings.starting_balance_usdt, equity, equity - settings.starting_balance_usdt, 0.0)
    return templates.TemplateResponse("reports.html", {"request": request, "summary": summary, "is_admin": _is_admin(request)})


@app.get("/state-monitor", response_class=HTMLResponse)
async def state_monitor(request: Request):
    if not _is_admin(request):
        return RedirectResponse(url="/login", status_code=302)

    db = SessionLocal()
    try:
        states = db.execute(text("SELECT symbol, state, latest_rsi, drop_blocks, rise_blocks, cooldown_until, panic_mode FROM bot_state ORDER BY symbol")).mappings().all()
    except SQLAlchemyError:
        states = []
    finally:
        db.close()
    return templates.TemplateResponse("state_monitor.html", {"request": request, "states": states, "now": datetime.now(timezone.utc), "is_admin": _is_admin(request)})
