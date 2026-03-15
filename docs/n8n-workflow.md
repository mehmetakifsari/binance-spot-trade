# n8n Workflow: Binance Signal -> Backend Bridge

Bu doküman, Coolify üzerinde çalışan mevcut mimaride Binance verisini alıp `bridge-service` üzerinden n8n'e taşıyarak backend `POST /api/signals` endpoint'ine nasıl ileteceğini adım adım anlatır.

> Not: n8n artık zorunlu değildir. İstersen backend içindeki internal collector (cron loop) ile n8n'yi tamamen devre dışı bırakabilirsin.
> Bunun için `SIGNAL_COLLECTOR_ENABLED=true` set edilmesi yeterlidir.

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

### 6.4) `Build Signal Payload` node'unda JavaScript / Python hataları

`Fetch Binance Klines` çıktısı, tek bir item içinde **array (liste)** döndürür.
Bu yüzden Code node'da örnek gelen `item.json.myNewField = 1` şablonu bu akışta doğrudan çalışmaz.

> Kritik: n8n bazen node dili değişince varsayılan örnek kodu geri yazar. `Build Signal Payload` içinde `myNewField` görüyorsan kod resetlenmiştir; tüm kodu silip bu dokümandaki örneği **tamamını** yapıştır.

#### Hata 1: JavaScript'te `A 'json' property isn't an object`

Bu hata, output'ta `json` alanına object yerine array bırakıldığında oluşur.
Bu akışta doğru yaklaşım, klines listesini okuyup **yeni bir object** dönmektir:

```javascript
const out = [];

for (const item of $input.all()) {
  const rows = item.json; // Binance klines: [[openTime, open, high, low, close, ...], ...]
  const closes = rows.map((r) => Number(r[4])).filter((v) => Number.isFinite(v));

  const price = closes[closes.length - 1];

  out.push({
    json: {
      symbol: 'BTCUSDT',
      price,
    },
  });
}

return out;
```

### 6.4.1) Aynı hatayı sürekli alıyorsan hızlı teşhis (5 dakika)

Bu hatanın kök nedeni neredeyse her zaman aynıdır: Code node bir noktada `return [{ json: [...] }]` ya da
`item.json = [...]` gibi bir şey üretir. n8n ise her item için `json` alanında **object** bekler.

Adım adım kontrol et:

1. Hata veren Code node'u aç ve `console.log` yerine geçici olarak aşağıdaki satırı en üste ekle:

```javascript
if (Array.isArray($json)) {
  throw new Error('Input doğrudan array geldi; önce object üretmelisin.');
}
```

2. Node ayarında **Mode** değerini kontrol et:
   - `Run Once for All Items` kullanıyorsan `return [{ json: { ... } }]` veya `return out` formatında dön.
   - `Run Once for Each Item` kullanıyorsan `return { ... }` (tek object) dön; `[{ json: ... }]` dönme.

3. Execution data'da bir önceki node çıktısını doğrula:
   - Eğer çıktı `[[...], [...]]` gibi nested list ise önce `Item Lists` / `Code` ile normalize et.
   - Hedef format her zaman şu olmalı: `[{ json: { key: value } }]`.

4. Node içinde `myNewField` veya default template geri geldiyse node resetlenmiştir; kodu tamamen silip yeniden yapıştır.

### 6.4.2) Alternatif yöntemler (Code node'a takılmadan)

Eğer Code node sürekli sorun çıkarıyorsa aşağıdaki iki yöntem daha stabil çalışır:

1. **Function Item / Edit Fields (Set) yaklaşımı**
   - Önce `HTTP Request` çıktısını `Set` node ile alan alan map et.
   - Ardından küçük bir `Code`/`Function Item` ile sadece RSI hesabını yap.
   - Bu şekilde tüm payload'ı tek yerde elle kurmazsın, `json` tipi daha az bozulur.

2. **Split + Aggregate yaklaşımı**
   - `Item Lists > Split Out Items` ile kline array'ini item'lara böl.
   - İhtiyaç alanlarını (`close`) çıkar.
   - Sonra `Code` node'da saf number listesi üzerinden RSI hesapla.
   - Özellikle import edilen workflow farklı n8n versiyonunda açıldığında daha az format hatası verir.

#### Hata 2: Python'da `list indices must be integers or slices, not str`

Bu hata, `item["json"]` gibi bir erişim denendiğinde görülür; çünkü bu akışta `item`
bir dict değil, doğrudan list (klines satırları) olur.

`Python (Native)` için aynı mantığın doğru kullanımı:

```python
out = []

for rows in _items:
    closes = [float(r[4]) for r in rows if len(r) > 4]
    price = closes[-1]

    out.append({
        "symbol": "BTCUSDT",
        "price": price,
    })

return out
```

#### Hata 3: Workflow JSON import sonrası Language alanı seçilemiyor

- Bu repodaki import workflow'lar varsayılan olarak `JavaScript` Code node ile gelir.
- Bazı n8n sürümlerinde/eski node versiyonlarında import edilen node'da dil alanı kilitli görünebilir.
- Çözüm: yeni bir Code node oluşturup `Language` seçimini o node'da yap, sonra kodu yapıştır.
- Alternatif: mevcut node'u silip aynı bağlantılarla tekrar ekle.

## 7) Olası Sorunlar

- **Bridge configured=false**
  - `N8N_WEBHOOK_URL` boş veya yanlış.
- **n8n webhook 404**
  - Path `visutrade-signal` değil veya workflow active değil.
- **Backend 422 validation error**
  - n8n payload alan isimleri backend model ile uyuşmuyor.
- **RSI hep 50**
  - Yeni boot sonrası yeterli price history birikmemiş olabilir.

- **HTTP Request/Set node'unda `{{$json.rsi}}` gibi alanlar `undefined`**
  - Webhook node'u bazı n8n sürümlerinde payload'ı `json.body` altında verir.
  - Bu durumda expression'ları geçici olarak `{{$json.body.rsi}}` gibi görürsün; kalıcı çözüm Normalize node'unda hem `json` hem `json.body` formatını desteklemektir (repo'daki import JSON bu desteği içerir).
  - `Build Signal Payload` node çıktısında `rsi`, `is_bearish`, `is_bullish`, `panic_score` alanlarının gerçekten üretildiğini execution data'dan doğrula.


## 8) Opsiyonel: n8n içinde Cron ile test akışı (bridge'e dokunmadan)

Evet, test için n8n tarafına ayrı bir **Cron workflow** ekleyebilirsin. Bu yöntem üretim akışını bozmaz:

- Üretim: `bridge-service -> /webhook/visutrade-signal` (aynı kalır)
- Test: `Schedule Trigger -> Binance REST klines -> /api/signals`

Bu repo içinde import edilebilir test workflow dosyası:

- `docs/n8n-workflow.cron-test.visutrade.json`

### Ne yapar?

1. Her 1 dakikada tetiklenir (`Schedule Trigger`).
2. Binance REST'ten candle verisi çeker (`/api/v3/klines?symbol=BTCUSDT&interval=15m&limit=200`).
3. RSI'yı candle close serisinden hesaplar (Binance endpoint RSI döndürmediği için).
4. Son close fiyatı ile flag'leri üretip backend `POST /api/signals` endpoint'ine yollar.

### Kullanım önerisi

- Bu cron workflow'u **sadece staging/test** ortamında aktif et.
- Aynı anda hem bridge webhook akışı hem cron test akışı açıksa backend'e daha sık sinyal gider.
- Test bitince cron workflow'u durdur.

## 9) `Send Signal` (HTTP Request) hatasını neden görüyoruz?

`Send Signal` node'unda görülen hataların çoğu, `dashboard` alanından değil, n8n -> backend çağrısının teknik detaylarından kaynaklanır. En sık sebepler:

1. **422 validation error (backend)**
   - `/api/signals` endpoint'i şu alanları bekler: `symbol`, `price`, `rsi`, `is_bearish`, `is_bullish`, `panic_score`.
   - n8n bu alanlardan birini eksik/farklı tipte gönderirse backend 422 döner.

2. **404 / 401 (webhook veya hedef URL)**
   - `webhook-test` ile `webhook` URL'lerinin karışması.
   - Workflow active olmadan production URL çağırılması.

3. **n8n expression / env kısıtı**
   - Bazı kurulumlarda `{{$env.*}}` kapalıdır; URL expression'ı çalışmaz.
   - Bu yüzden HTTP Request URL alanında doğrudan sabit URL kullanımı daha güvenlidir.

4. **Timeout / geçici ağ hatası**
   - n8n'den backend'e giden tekil HTTP çağrısı anlık ağ dalgalanmasında fail olabilir.

## 10) "Dashboard zaten Cron ile veri almıyor mu?"

Bu repodaki üretim tasarımında dashboard veri kaynağı doğrudan Cron değildir.

- **Ana üretim akışı:** `bridge-service (Binance WS) -> n8n webhook -> backend /api/signals -> dashboard`
- **Cron workflow:** sadece opsiyonel test/staging veya fallback için önerilir.

Yani dashboard güncellemesi backend'e düşen sinyal kayıtlarından gelir; Cron zorunlu değil, ek bir tetikleme seçeneğidir.

## 11) HTTP request ile sinyal göndermenin daha sağlıklı yolları

Evet, tek node ile "fire-and-forget" yerine daha dayanıklı bir desen kurabilirsin:

1. **Retry + backoff (n8n HTTP Request ayarı)**
   - HTTP Request node'da retry aç.
   - 5xx/timeout için yeniden deneme uygula.

2. **Idempotency key ekle**
   - Aynı sinyal birden fazla kez gönderilirse backend tarafında duplicate etkisini azaltırsın.
   - Örn: `symbol + event_time` tabanlı bir `signal_id` gönder.

3. **Queue tabanlı ara katman (en sağlam yöntem)**
   - n8n doğrudan backend yerine bir kuyruk/stream'e yazar (Redis stream, RabbitMQ, SQS vb.).
   - Backend worker kuyruktan okuyup işler.
   - Ağ kesintisi anında veri kaybı riski ciddi azalır.

4. **Bridge doğrudan backend + n8n gözlemci modeli**
   - Kritik path'te bridge doğrudan `/api/signals` endpoint'ine yazar.
   - n8n'i analitik/alert/rapor için yan kanal yaparsın.

5. **Devre kesici (circuit breaker) / DLQ yaklaşımı**
   - Belirli sayıda başarısız denemede akışı DLQ'ya yönlendir.
   - Sonradan tekrar işlenebilir sinyal havuzu tut.
