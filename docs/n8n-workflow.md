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
   - URL: `https://api-trade.visupanel.com/api/signals`
   - Body JSON:
     - `symbol`
     - `price`
     - `rsi`
     - `is_bearish`
     - `is_bullish`
     - `panic_score`

> Not: Bazı n8n kurulumlarında node expression içinde `{{$env.*}}` kullanımı güvenlik nedeniyle kapalıdır ve
> `access to env vars denied` hatası verir. Bu repo içindeki import workflow'ları bu nedenle sabit URL ile gelir.
> URL değiştirmek için HTTP Request node içindeki `URL` alanını doğrudan düzenle.

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


## 5.1) Coolify'de **bridge-service / N8N_WEBHOOK_URL** alanına ne yazılmalı?

Bridge servisi tarafında girmen gereken değer **n8n Webhook node'unun Production URL'i** olmalı.

Doğru format:

- `https://<n8n-domain>/webhook/visutrade-signal`

Örnek:

- `https://n8n.visupanel.com/webhook/visutrade-signal`

> Notlar:
> - `.../webhook-test/...` adresi sadece n8n editörde test içindir; bridge için production'da bunu kullanma.
> - Path, workflow'daki Webhook node path'i ile aynı olmalı (`visutrade-signal`).
> - Workflow **Active** değilse production webhook 404/401 dönebilir.


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

### 6.1) n8n tarafında hızlı smoke test (bridge olmadan)

Önce workflow logic'in çalıştığını doğrulamak için bridge'i beklemeden Webhook node'unu test et:

1. n8n editörde workflow'u aç.
2. **Webhook Trigger** node'una girip **Listen for test event** başlat.
3. Aşağıdaki örnek payload'ı **test URL**'e gönder:

```bash
curl -X POST 'https://<n8n-domain>/webhook-test/visutrade-signal' \
  -H 'Content-Type: application/json' \
  -d '{
    "source": "binance_ws",
    "stream": "wss://stream.binance.com:9443/ws/btcusdt@trade",
    "received_at": "2026-01-01T10:00:00Z",
    "data": {
      "e": "trade",
      "E": 1735725600000,
      "s": "BTCUSDT",
      "p": "43000.12"
    }
  }'
```

Beklenen sonuç:

- `Normalize Binance Event` node'unda `symbol` ve `price` dolu olmalı.
- `Build Signal Payload` node'unda `rsi`, `is_bearish`, `is_bullish`, `panic_score` oluşmalı.
- `POST Backend /api/signals` node'unda HTTP `200` dönmeli.

> Not: `webhook-test` URL sadece editor test modunda çalışır. Bridge service production'da bunu kullanmaz.

### 6.2) end-to-end test (bridge + production webhook)

Smoke test sonrası production davranışı için:

1. Workflow'u **Active** yap.
2. `bridge-service` env'de `N8N_WEBHOOK_URL=https://<n8n-domain>/webhook/visutrade-signal` olduğundan emin ol.
3. Bridge servisini redeploy/restart et.
4. Bridge health kontrolü:

```bash
curl -s 'https://<bridge-domain>/health'
```

Beklenen alanlar:

- `configured: true`
- `running: true`
- kısa süre sonra `last_message_at` dolu

5. n8n executions ekranında yeni production execution'ları gör.

### 6.3) En sık test hataları

- **404 on webhook**: workflow active değil veya path yanlış (`visutrade-signal` olmalı).
- **422 from backend**: n8n payload alanları backend modeli ile uyuşmuyor.
- **No executions**: bridge tarafında `N8N_WEBHOOK_URL` yanlış/boş veya bridge redeploy edilmemiş.

### 6.4) `Build Signal Payload` node'unda Python (Native) hatası

Mobilde düzenleme yaparken n8n'in örnek kodu yanlış satır kırılırsa şu tip bir syntax hatası oluşur:

```python
item["json"]
["my_new_field"] = 1
```

Yukarıdaki kullanımda ikinci satır yeni bir liste gibi yorumlandığı için node fail olur.

Eğer **Language = Python (Native)** kullanacaksan kodu aşağıdaki gibi tek satır erişimle yaz:

```python
for item in _items:
    item["json"]["my_new_field"] = 1

return _items
```

> Notlar:
> - `Run Once for All Items` modunda `for item in _items` kullan.
> - `Run Once for Each Item` modunda `_item` kullanıp tek obje dön.
> - Bu repodaki import workflow'lar varsayılan olarak `JavaScript` Code node ile gelir; Python'a geçersen kodu tamamen Python sözdizimiyle güncelle.

## 7) Olası Sorunlar

- **Bridge configured=false**
  - `N8N_WEBHOOK_URL` boş veya yanlış.
- **n8n webhook 404**
  - Path `visutrade-signal` değil veya workflow active değil.
- **Backend 422 validation error**
  - n8n payload alan isimleri backend model ile uyuşmuyor.
- **RSI hep 50**
  - Yeni boot sonrası yeterli price history birikmemiş olabilir.


## 8) Opsiyonel: n8n içinde Cron ile test akışı (bridge'e dokunmadan)

Evet, test için n8n tarafına ayrı bir **Cron workflow** ekleyebilirsin. Bu yöntem üretim akışını bozmaz:

- Üretim: `bridge-service -> /webhook/visutrade-signal` (aynı kalır)
- Test: `Schedule Trigger -> Binance REST ticker -> /api/signals`

Bu repo içinde import edilebilir test workflow dosyası:

- `docs/n8n-workflow.cron-test.visutrade.json`

### Ne yapar?

1. Her 1 dakikada tetiklenir (`Schedule Trigger`).
2. Binance REST'ten anlık fiyat çeker (`/api/v3/ticker/price?symbol=BTCUSDT`).
3. n8n static data ile RSI + flag hesaplar.
4. Backend `POST /api/signals` endpoint'ine yollar.

### Kullanım önerisi

- Bu cron workflow'u **sadece staging/test** ortamında aktif et.
- Aynı anda hem bridge webhook akışı hem cron test akışı açıksa backend'e daha sık sinyal gider.
- Test bitince cron workflow'u durdur.
