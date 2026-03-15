# Architecture Notes

## Design principles

- Paper trading only (no live order endpoints)
- Deterministic, rule-based signal engine
- Modular services for Coolify deployment
- Environment-driven configuration

## Service boundaries

1. **Bridge Service**
   - Connects to Binance Spot websocket stream
   - Normalizes and forwards market data to n8n webhook
   - Exposes `/health` (bridge)
   - Handles reconnect with backoff

2. **n8n Workflow (optional)**
   - Receives bridge payload
   - Can enrich/transforms data
   - Calls backend `/api/signals` with normalized signal payload

3. **Backend Service**
   - Runs deterministic state machine
   - Executes paper-trading calculations
   - Persists state and trades in PostgreSQL
   - Sends Telegram events
   - Serves MVP dashboard pages
   - Optional internal signal collector (cron loop) can fetch Binance klines and produce `/api/signals` payloads without n8n

4. **PostgreSQL**
   - Stores bot state, trades, positions, snapshots, report cache

## State machine sketch

- `NEUTRAL` -> `WATCH_DROP` -> `WAIT_CONFIRM` -> `BUY_READY` -> `BOUGHT`
- Panic branch: `WATCH_DROP` -> `PANIC_WAIT` -> `PANIC_BOUGHT`
- Post-buy: `BOUGHT` -> `WATCH_RISE` -> `SOLD` -> `COOLDOWN` -> `NEUTRAL`

## Deterministic trading constraints

- Two bearish moves increment one drop block.
- Buy only after >=1 drop block and rebound confirmation.
- Two bullish moves increment one rise block.
- Safe sell at 3 rise blocks or defensive exhaustion after >=1 block.
- Cooldown enforced after every buy/sell.

## AI usage policy

AI outputs are optional and non-executing:
- explain "why a deterministic trade happened"
- summarize daily/weekly/monthly performance

AI cannot choose buy/sell actions.


## Domain plan (Coolify)

- Frontend panel domain: `trade.visupanel.com`
- Backend API domain: `api-trade.visupanel.com`
- Backend must allow frontend origin via CORS configuration.
