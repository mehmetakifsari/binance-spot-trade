# VisuTrade Paper Signal Engine (MVP)

VisuTrade is a **Binance Spot paper-trading signal engine** designed for safe MVP validation.

> ✅ This version is **paper trading only**.
> ❌ No live Binance order placement is implemented.

## Scope (Current)

This repository includes:

- Phase 1: Project structure, architecture, and setup documentation
- Phase 2: Binance WebSocket bridge service (Binance -> n8n webhook)
- Phase 3: PostgreSQL schema + migration
- Phase 4: Backend foundation for deterministic state machine + paper trading
- Phase 5: MVP web panel pages (Dashboard, Trades, Reports, State Monitor)
- Phase 6: Telegram notifier foundation (trade/error/summary)
- Phase 7: Coolify deployment notes

## High-Level Architecture

`Binance WebSocket -> Bridge Service -> n8n Webhook -> Signal Engine -> Paper Trade Logic -> PostgreSQL -> Telegram -> Web Dashboard`

Production domain target (Coolify):
- Frontend: `https://trade.visupanel.com`
- Backend API: `https://api-trade.visupanel.com`

See [docs/architecture.md](docs/architecture.md) and [docs/coolify-deployment.md](docs/coolify-deployment.md) for details.

## Repository Structure

```text
.
├── bridge_service/            # Binance websocket listener + webhook forwarder
│   ├── app/
│   ├── Dockerfile
│   └── requirements.txt
├── backend/                   # State machine, paper trading, API, dashboard views
│   ├── app/
│   ├── templates/
│   ├── static/
│   ├── Dockerfile
│   └── requirements.txt
├── migrations/
│   └── 001_init.sql           # Initial PostgreSQL schema
├── frontend/                  # Nginx reverse proxy for trade.visupanel.com
│   ├── Dockerfile
│   └── nginx.conf.template
├── docs/
│   ├── architecture.md
│   ├── schema.md
│   └── coolify-deployment.md
├── .env.example
└── docker-compose.yml         # Local dev stack
```

## Quick Start (Local)

1. Copy env file:

```bash
cp .env.example .env
```

2. Start stack:

```bash
docker compose up --build
```

3. Apply DB migration:

```bash
docker compose exec postgres psql -U "$DB_USER" -d "$DB_NAME" -f /docker-entrypoint-initdb.d/001_init.sql
```

4. Run backend unit tests:

```bash
cd backend && pip install -r requirements.txt && pytest
```

5. Check health:

- Frontend (proxy) health: `http://localhost:8080/healthz`
- Frontend dashboard URL: `http://localhost:8080/dashboard`
- Backend health: `http://localhost:8000/api/health`
- Bridge health (internal in Docker network): `http://bridge:8001/health`

## Core Trading Rules (Deterministic)

- Buy after bearish block analysis + rebound confirmation
- Sell based on rise blocks / defensive exhaustion
- Panic protection mode for abnormal drops
- Cooldown after each BUY/SELL
- States include `NEUTRAL`, `WATCH_DROP`, `WAIT_CONFIRM`, `BUY_READY`, `BOUGHT`, `PANIC_WAIT`, `PANIC_BOUGHT`, `WATCH_RISE`, `SOLD`, `COOLDOWN`

The backend keeps trade decisions deterministic and rule-based. Any AI service can only generate explanations/reports.

## Security & Config

- All secrets/config are read from environment variables.
- Never commit real API keys.
- `OPENAI_API_KEY` is optional and must never execute trade decisions.

## API Endpoints

- Health: `GET /api/health`
- Signal ingest (n8n -> backend): `POST /api/signals`

## TODOs (MVP-next)

- Connect n8n workflow payload format to `/signals` endpoint end-to-end
- Add auth for dashboard endpoints
- Add background scheduler for end-of-day / weekly / monthly report jobs
- Add integration tests for state transitions and PnL calculations

