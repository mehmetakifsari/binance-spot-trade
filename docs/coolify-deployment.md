# Coolify Deployment Notes

Bu proje Coolify üzerinde iki ana domain ile çalışacak şekilde tasarlanmıştır:

- Frontend panel: `https://trade.visupanel.com`
- Backend API: `https://api-trade.visupanel.com`

## Services

1. `bridge-service` (Dockerfile: `bridge_service/Dockerfile`)
2. `backend-service` (Dockerfile: `backend/Dockerfile`)
3. `frontend-service` (Dockerfile: `frontend/Dockerfile`, nginx reverse proxy)
4. `postgres` managed DB resource
5. optional `n8n` service resource

## Domain mapping (Coolify)

### Backend service
- Domain: `api-trade.visupanel.com`
- Port: `8000`
- Healthcheck: `/api/health`

### Frontend service
Bu repoda `frontend/` altında nginx reverse proxy eklidir ve `trade.visupanel.com` için önerilen kurulum budur.

- Domain: `trade.visupanel.com`
- Port: `8080`
- Healthcheck: `/healthz`
- Runtime env: `BACKEND_ORIGIN=http://backend-service:8000` (Coolify internal URL)

Proxy davranışı:
- `/` -> `/dashboard` yönlendirmesi yapar.
- Tüm istekleri backend servise iletir (dashboard + API).

> Not: Dashboard template backend içinde render edilmeye devam eder; frontend servis sadece domain ayrımı için reverse proxy görevi görür.

## Environment variables

Required:
- `BINANCE_STREAM`
- `DB_HOST`
- `DB_PORT`
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `APP_ENV`
- `FRONTEND_BASE_URL`
- `BACKEND_BASE_URL`
- `CORS_ALLOWED_ORIGINS`

Optional:
- `N8N_WEBHOOK_URL` (unset ise bridge worker pasif başlar, servis yine ayağa kalkar)
- `OPENAI_API_KEY` (explanation/report text only)

## Deployment order

1. Deploy PostgreSQL and capture connection credentials.
2. Deploy backend service (`api-trade.visupanel.com`) with DB + Telegram + URL/CORS env vars.
3. Run SQL migration `migrations/001_init.sql`.
4. Deploy frontend reverse-proxy service (`trade.visupanel.com`) with `BACKEND_ORIGIN` set to backend internal URL.
5. Deploy bridge service with Binance + n8n vars.
6. Configure n8n workflow to call backend `POST /api/signals` endpoint.

## Service relationships

- Bridge -> n8n webhook
- n8n -> backend `/api/signals`
- Backend -> PostgreSQL
- Backend -> Telegram Bot API

## Health checks

- Bridge: `GET /health`
- Backend: `GET /api/health`
- Frontend proxy: `GET /healthz`
