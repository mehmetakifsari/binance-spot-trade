# n8n Workflow: Binance Signal -> Backend Bridge

Bu doküman, Coolify üzerinde çalışan mevcut mimaride Binance verisini alıp `bridge-service` üzerinden n8n'e taşıyarak backend `POST /api/signals` endpoint'ine nasıl ileteceğini adım adım anlatır.

## 1) Akış Özeti

Bu repodaki data flow şu şekilde tasarlanmıştır:

1. `bridge-service` Binance WebSocket'ten ham event alır.
2. Her event'i n8n Webhook Trigger'a JSON olarak forward eder.
3. n8n, event içinden fiyatı çıkarır ve RSI hesaplar.
4. n8n, backend `POST /api/signals` endpoint'ine normalize edilmiş payload gönderir.

Bridge tarafı event'i n8n'e şu envelope ile gönderir:

```json
{
  "source": "binance_ws",
  "stream": "wss://stream.binance.com:9443/ws/btcusdt@trade",
  "received_at": "2026-01-01T10:00:00.000000+00:00",
  "data": {
    "e": "trade",
    "E": 1735725600000,
    "s": "BTCUSDT",
    "p": "43000.12"
  }
}
```

## 2) Ön Koşullar

- `bridge-service` ayakta ve `N8N_WEBHOOK_URL` doğru set edilmiş olmalı.
- n8n servisi public/internal URL'de erişilebilir olmalı.
- Backend erişimi olmalı: `https://api-trade.visupanel.com/api/signals`.

## 3) n8n Workflow Node Tasarımı

Önerilen minimum node zinciri:

1. **Webhook (Trigger)**
   - Method: `POST`
   - Path: `visutrade-signal`
   - Response: `Last Node`

2. **Code (Normalize Binance Event)**
   - Bridge'den gelen farklı Binance stream formatlarını tek tipe çevirir.
   - `trade`, `aggTrade`, `kline`, `miniTicker` gibi event'lerden fiyat/symbol çıkarmaya çalışır.

3. **Code (RSI + Flags)**
   - `workflow static data` içinde son fiyatları tutar.
   - Basit 14 period RSI hesaplar.
   - `is_bearish`, `is_bullish`, `panic_score` üretir.

4. **HTTP Request (Send Signal to Backend)**
   - Method: `POST`
   - URL: `{{$env.BACKEND_SIGNAL_URL || 'https://api-trade.visupanel.com/api/signals'}}`
   - Body JSON:
     - `symbol`
     - `price`
     - `rsi`
     - `is_bearish`
     - `is_bullish`
     - `panic_score`

## 4) Import Edilebilir Workflow

Aşağıdaki JSON dosyasını n8n'e import ederek direkt başlayabilirsin:

- `docs/n8n-workflow.visutrade.json`

Import sonrası yapılacaklar:

1. Workflow'u aç.
2. HTTP Request node URL'ini kendi backend adresinle doğrula.
3. Webhook Production URL'ini al.
4. Bu URL'yi `N8N_WEBHOOK_URL` olarak `bridge-service` env'e yaz.
5. Bridge servisini restart et.

## 5) Önerilen Coolify Env Değerleri

### bridge-service

- `BINANCE_STREAM=wss://stream.binance.com:9443/ws/btcusdt@trade`
- `N8N_WEBHOOK_URL=https://<n8n-domain>/webhook/visutrade-signal`

### n8n

- `BACKEND_SIGNAL_URL=https://api-trade.visupanel.com/api/signals`

## 6) Test Planı (Canlıya Almadan)

1. n8n'de workflow `Active` olsun.
2. `bridge-service /health` çağrısında:
   - `configured: true`
   - `running: true`
3. n8n executions ekranında yeni run'lar görünmeli.
4. backend log'unda `/api/signals` 200 dönmeli.
5. Dashboard tarafında state ve equity güncellenmeli.

## 7) Olası Sorunlar

- **Bridge configured=false**
  - `N8N_WEBHOOK_URL` boş veya yanlış.
- **n8n webhook 404**
  - Path `visutrade-signal` değil veya workflow active değil.
- **Backend 422 validation error**
  - n8n payload alan isimleri backend model ile uyuşmuyor.
- **RSI hep 50**
  - Yeni boot sonrası yeterli price history birikmemiş olabilir.

