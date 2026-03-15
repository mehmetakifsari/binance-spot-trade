# Coolify Deployment Notes

Bu proje Coolify üzerinde iki ana domain ile çalışacak şekilde tasarlanmıştır:

- Frontend panel: `https://trade.visupanel.com`
- Backend API: `https://api-trade.visupanel.com`

## Services

1. `bridge-service` (Dockerfile: `bridge_service/Dockerfile`)
2. `backend-service` (Dockerfile: `backend/Dockerfile`)
3. `postgres` managed DB resource
4. optional `n8n` service resource

## Domain mapping (Coolify)

### Backend service
- Domain: `api-trade.visupanel.com`
- Port: `8000`
- Healthcheck: `/api/health`

### Frontend service
MVP'de dashboard backend içinde render edildiği için iki seçenek vardır:

1. **Hızlı MVP (önerilen)**: Ayrı frontend servisi açmadan, dashboard'u backend'den servis et:
   - URL: `https://api-trade.visupanel.com/dashboard`
2. **İstenen domain yapısı** (`trade.visupanel.com`) için:
   - Ayrı bir frontend service (ör. static reverse proxy veya ayrı UI app) deploy edin.
   - Frontend API target: `https://api-trade.visupanel.com`

> Not: Bu repoda API + template dashboard tek backend servisinde tutulmuştur; domain ayrımı environment ve CORS ile desteklenir.

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
4. Deploy bridge service with Binance + n8n vars.
5. Configure n8n workflow to call backend `POST /api/signals` endpoint.
6. (Optional) Deploy dedicated frontend service for `trade.visupanel.com`.

## Service relationships

- Bridge -> n8n webhook
- n8n -> backend `/api/signals`
- Backend -> PostgreSQL
- Backend -> Telegram Bot API

## Health checks

- Bridge: `GET /health`
- Backend: `GET /api/health`
