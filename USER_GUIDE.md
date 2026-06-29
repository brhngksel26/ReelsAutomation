# Reels Automation — Kullanıcı Rehberi

Bu rehber, **Reels Automation** backend servisini uçtan uca nasıl kullanacağınızı anlatır: hesap açma, kanal yönetimi, platform bağlama, video planlama ve LangGraph tabanlı otomasyon agent'ını çalıştırma.

> **API dokümantasyonu:** Servis çalışırken [http://localhost:8000/docs](http://localhost:8000/docs) adresinden Swagger UI'ya erişebilirsiniz.

---

## İçindekiler

1. [Proje nedir?](#1-proje-nedir)
2. [Kurulum](#2-kurulum)
3. [Hesap oluşturma ve giriş](#3-hesap-oluşturma-ve-giriş)
4. [Kanal oluşturma ve yönetimi](#4-kanal-oluşturma-ve-yönetimi)
5. [RSS haber kaynakları (feed) ve kanal bağlama](#5-rss-haber-kaynakları-feed-ve-kanal-bağlama)
6. [Sosyal medya platformlarını bağlama](#6-sosyal-medya-platformlarını-bağlama)
7. [Video planlama (manuel akış)](#7-video-planlama-manuel-akış)
8. [Agent (Pipeline) nasıl çalışır?](#8-agent-pipeline-nasıl-çalışır)
9. [Agent'ı çalıştırma](#9-agentı-çalıştırma)
10. [Video durumunu takip etme](#10-video-durumunu-takip-etme)
11. [Önerilen iş akışı](#11-önerilen-iş-akışı)
12. [Gerekli harici servisler](#12-gerekli-harici-servisler)
13. [Pipeline bildirimleri (ntfy)](#13-pipeline-bildirimleri-ntfy)
14. [Sık karşılaşılan sorunlar](#14-sık-karşılaşılan-sorunlar)

---

## 1. Proje nedir?

Reels Automation, Instagram Reels, YouTube Shorts ve TikTok için kısa video üretim ve yayınlama sürecini otomatikleştiren bir **FastAPI backend**'idir.

Temel bileşenler:

| Bileşen | Görev |
|---------|-------|
| **REST API** | Kullanıcı, kanal, platform ve video yönetimi |
| **LangGraph Agent** | Fikir üretimi → doğrulama → senaryo → video üretimi → yayınlama |
| **LLM** (Ollama / OpenAI vb.) | Video fikri ve senaryo üretimi |
| **MoneyPrinterTurbo** | Seslendirme ve görsel video montajı |
| **Celery + Redis** | Arka plan görevleri ve zamanlanmış tetiklemeler |
| **PostgreSQL** | Kullanıcı, kanal, video ve pipeline durumu |
| **RSS entegrasyonu** | Haber kaynaklarını tarar, kanala bağlar, agent'a haber bağlamı sağlar |

---

## 2. Kurulum

### Gereksinimler

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) paket yöneticisi
- Docker & Docker Compose (önerilir)
- Harici servisler: PostgreSQL, Redis, LLM, MoneyPrinterTurbo (aşağıda detaylı)

### Hızlı başlangıç (yerel)

```bash
cp .env.example .env
docker compose up -d reels_automation_database reels_automation_redis
uv sync
uv run alembic upgrade head
uv run uvicorn src.main:app --reload --port 8000
```

### Celery worker ve beat (zorunlu — agent ve zamanlanmış görevler için)

Agent ve otomatik yayınlama için Celery çalışmalıdır:

```bash
# Terminal 1 — worker
uv run celery -A src.core.celery_app worker --loglevel=info

# Terminal 2 — beat (zamanlayıcı)
uv run celery -A src.core.celery_app beat --loglevel=info
```

Docker Compose ile tüm stack'i ayağa kaldırmak için:

```bash
docker compose up --build
```

### Smoke test

Kurulumun çalıştığını doğrulamak için:

```bash
uv run python scripts/smoke_test.py
```

---

## 3. Hesap oluşturma ve giriş

Tüm korumalı endpoint'ler **JWT Bearer token** gerektirir. Kayıt sonrası aldığınız token'ı her istekte `Authorization` header'ına ekleyin.

### 3.1 Kayıt ol

**Endpoint:** `POST /api/v1/auth/register`

| Alan | Zorunlu | Açıklama |
|------|---------|----------|
| `email` | Evet | Geçerli e-posta adresi |
| `password` | Evet | En az 8 karakter |
| `first_name` | Hayır | Ad |
| `last_name` | Hayır | Soyad |

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "ornek@example.com",
    "password": "guvenlisifre123",
    "first_name": "Ali",
    "last_name": "Yılmaz"
  }'
```

**Başarılı yanıt (201):**

```json
{
  "id": 1,
  "email": "ornek@example.com",
  "is_active": true,
  "is_verified": false
}
```

Kayıt sırasında otomatik olarak:
- `free` tier profil oluşturulur
- Varsayılan izinler (kanal, platform, video işlemleri) atanır

### 3.2 Giriş yap ve token al

**Endpoint:** `POST /api/v1/auth/token`

OAuth2 form formatında gönderilir (`username` alanına e-posta yazılır):

```bash
curl -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=ornek@example.com&password=guvenlisifre123"
```

**Başarılı yanıt (200):**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

Token varsayılan olarak **60 dakika** geçerlidir (`.env` içindeki `ACCESS_TOKEN_EXPIRE_MINUTES` ile ayarlanır).

### 3.3 Profil bilgisi

**Endpoint:** `GET /api/v1/users/me`

```bash
curl http://localhost:8000/api/v1/users/me \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

---

## 4. Kanal oluşturma ve yönetimi

Kanal, içerik üretiminin merkezidir. Niş, hedef kitle, dil, ton ve agent'ın kullanacağı `system_prompt` burada tanımlanır.

### 4.1 Kanal oluştur

**Endpoint:** `POST /api/v1/channels/`

| Alan | Zorunlu | Açıklama |
|------|---------|----------|
| `name` | Evet | Kanal adı |
| `niche` | Evet | İçerik nişi (ör. Finance, Fitness) |
| `target_audience` | Evet | Hedef kitle |
| `language` | Evet | Dil kodu (ör. `tr`, `en`) |
| `tone_of_voice` | Evet | İçerik tonu (ör. motivational, friendly) |
| `system_prompt` | Hayır | LLM'e özel talimatlar |
| `daily_video_count` | Hayır | Günlük video hedefi (1–50, varsayılan: 1) |
| `posting_hours` | Hayır | Sabit saat modunda otomatik agent tetikleme saatleri (`HH:MM:SS`) |
| `scheduling_mode` | Hayır | `fixed_hours` (varsayılan) veya `rss_news` |
| `rss_interval_minutes` | Hayır | RSS modunda videolar arası dakika (varsayılan: 30) |
| `rss_max_videos_per_day` | Hayır | RSS modunda günlük üst limit (varsayılan: 20) |
| `base_hashtags` | Hayır | Kanalın varsayılan hashtag'leri |
| `is_active` | Hayır | Aktif/pasif (varsayılan: `true`) |

#### Sabit saat modu (`fixed_hours`)

Geleneksel kullanım: belirli saatlerde agent tetiklenir.

```bash
curl -X POST http://localhost:8000/api/v1/channels/ \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Finans İpuçları",
    "niche": "Finance",
    "target_audience": "Genç profesyoneller",
    "language": "tr",
    "tone_of_voice": "motivational",
    "system_prompt": "Kısa, etkileyici finans reels içerikleri üret",
    "scheduling_mode": "fixed_hours",
    "daily_video_count": 2,
    "posting_hours": ["12:00:00", "18:00:00"],
    "base_hashtags": ["finans", "para", "yatırım"]
  }'
```

`posting_hours` alanı bu modda önemlidir: Celery beat her dakika kontrol eder ve saat eşleştiğinde agent'ı otomatik tetikler (kanal `is_active: true` ise).

#### RSS haber modu (`rss_news`)

Haber kaynaklarından gelen güncel içeriklerle otomatik video üretimi için kanalı bu modda oluşturun. `posting_hours` boş bırakılabilir.

```bash
curl -X POST http://localhost:8000/api/v1/channels/ \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Teknoloji Haberleri",
    "niche": "Technology",
    "target_audience": "Teknoloji meraklıları",
    "language": "tr",
    "tone_of_voice": "informative",
    "system_prompt": "Güncel teknoloji haberlerini kısa ve anlaşılır reels formatında anlat",
    "scheduling_mode": "rss_news",
    "daily_video_count": 10,
    "rss_interval_minutes": 30,
    "rss_max_videos_per_day": 20,
    "posting_hours": [],
    "base_hashtags": ["teknoloji", "haber", "gündem"]
  }'
```

RSS modunda:
- Günde kaç video üretileceği: `min(kullanılmamış haber sayısı, daily_video_count, rss_max_videos_per_day)`
- Videolar `rss_interval_minutes` arayla planlanır (ör. 30 dk → 10 haber = 5 saatlik pencere)
- Kanal oluşturduktan sonra [Bölüm 5](#5-rss-haber-kaynakları-feed-ve-kanal-bağlama) ile feed yetkisi vermeniz gerekir

### 4.2 Kanalları listele

**Endpoint:** `GET /api/v1/channels/`

```bash
curl "http://localhost:8000/api/v1/channels/?skip=0&limit=100" \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

### 4.3 Kanal güncelle

**Endpoint:** `PUT /api/v1/channels/{channel_id}`

Sadece değiştirmek istediğiniz alanları gönderin.

```bash
curl -X PUT http://localhost:8000/api/v1/channels/1 \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "daily_video_count": 3,
    "posting_hours": ["09:00:00", "15:00:00", "21:00:00"]
  }'
```

### 4.4 Kanal sil

**Endpoint:** `DELETE /api/v1/channels/{channel_id}`

```bash
curl -X DELETE http://localhost:8000/api/v1/channels/1 \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

---

## 5. RSS haber kaynakları (feed) ve kanal bağlama

RSS feed'ler sistemde **global bir katalog** olarak tutulur. Her feed bir "tool" (haber kaynağı) gibidir. Kanallara hangi feed'lere erişebileceği ayrıca yetkilendirilir; haberler global havuzda toplanır, hangi kanalın hangi haberi kullandığı kanal bazında izlenir.

### 5.1 Kavramlar

| Kavram | Açıklama |
|--------|----------|
| **RSS Feed** | Haber kaynağı (ör. TechCrunch, OpenAI Blog) |
| **Feed yetkisi** | Kanalın hangi feed'lerden haber alabileceği |
| **Kullanılmamış haber** | Kanalın daha önce video üretmediği haber |
| **RSS scrape** | Feed'lerin günde 1 kez taranıp DB'ye kaydedilmesi |

Migration ile varsayılan olarak şu feed'ler seed edilir: MIT Technology Review, OpenAI Blog, The Verge, Ars Technica, CoinDesk, Phys.org.

### 5.2 Mevcut feed'leri listele

**Endpoint:** `GET /api/v1/rss/feeds`

```bash
curl http://localhost:8000/api/v1/rss/feeds \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

**Yanıt örneği:**

```json
[
  {
    "id": 1,
    "name": "MIT Technology Review",
    "url": "https://www.technologyreview.com/feed/",
    "category": "tech",
    "is_active": true
  }
]
```

### 5.3 Yeni feed ekle (isteğe bağlı)

Sisteme yeni bir haber kaynağı eklemek için:

**Endpoint:** `POST /api/v1/rss/feeds`

```bash
curl -X POST http://localhost:8000/api/v1/rss/feeds \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "TechCrunch",
    "url": "https://techcrunch.com/feed/",
    "category": "tech",
    "is_active": true
  }'
```

### 5.4 Kanala RSS feed yetkisi ver

Kanal oluşturduktan sonra (veya mevcut bir kanala) feed bağlamak için feed ID'lerini gönderin.

**Endpoint:** `POST /api/v1/rss/channels/{channel_id}/feeds`

```bash
curl -X POST http://localhost:8000/api/v1/rss/channels/1/feeds \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "feed_ids": [1, 2, 3]
  }'
```

Bu işlem kanala "tool" yetkisi verir. Agent çalıştığında yalnızca bu feed'lerden gelen ve o kanalda daha önce kullanılmamış haberler seçilir.

### 5.5 Kanalın feed'lerini listele

**Endpoint:** `GET /api/v1/rss/channels/{channel_id}/feeds`

```bash
curl http://localhost:8000/api/v1/rss/channels/1/feeds \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

### 5.6 Feed yetkisini kaldır

**Endpoint:** `DELETE /api/v1/rss/channels/{channel_id}/feeds/{feed_id}`

```bash
curl -X DELETE http://localhost:8000/api/v1/rss/channels/1/feeds/2 \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

### 5.7 Kanalın haberlerini görüntüle

**Endpoint:** `GET /api/v1/rss/channels/{channel_id}/news`

```bash
curl "http://localhost:8000/api/v1/rss/channels/1/news?skip=0&limit=50" \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

### 5.8 Haber taramasını tetikle

Feed'ler günde 1 kez otomatik taranır (varsayılan: 06:00 UTC). Manuel tetiklemek için:

**Endpoint:** `POST /api/v1/rss/scrape`

```bash
curl -X POST http://localhost:8000/api/v1/rss/scrape \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

Tarama bittikten sonra `scheduling_mode: rss_news` olan kanallar için pipeline'lar otomatik planlanır.

### 5.9 RSS kanalı için pipeline planlamayı manuel tetikle

**Endpoint:** `POST /api/v1/rss/channels/{channel_id}/schedule`

```bash
curl -X POST "http://localhost:8000/api/v1/rss/channels/1/schedule?force=false" \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

| Parametre | Açıklama |
|-----------|----------|
| `force=false` | Bugün zaten planlandıysa tekrar planlamaz (varsayılan) |
| `force=true` | Aynı gün tekrar planlamaya izin verir |

**Yanıt örneği:**

```json
{
  "channel_id": 1,
  "scheduled_videos": 10,
  "interval_minutes": 30
}
```

Bu örnekte 10 pipeline görevi kuyruğa alınır: ilki hemen, sonrakiler 30'ar dakika arayla.

### 5.10 RSS kanalı kurulumu — uçtan uca örnek

```bash
# 1) RSS modunda kanal oluştur
curl -X POST http://localhost:8000/api/v1/channels/ \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "AI Haberleri",
    "niche": "Artificial Intelligence",
    "target_audience": "Geliştiriciler",
    "language": "en",
    "tone_of_voice": "clear",
    "system_prompt": "Explain AI news in simple short-form video scripts",
    "scheduling_mode": "rss_news",
    "daily_video_count": 10,
    "rss_interval_minutes": 30,
    "rss_max_videos_per_day": 20,
    "posting_hours": [],
    "base_hashtags": ["ai", "news"]
  }'

# 2) Mevcut feed'leri listele ve ID'leri al
curl http://localhost:8000/api/v1/rss/feeds -H "Authorization: Bearer <TOKEN>"

# 3) Kanala feed yetkisi ver (ör. OpenAI + The Verge)
curl -X POST http://localhost:8000/api/v1/rss/channels/1/feeds \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"feed_ids": [2, 3]}'

# 4) Platform bağla (Bölüm 6)
# 5) Haber taramasını başlat
curl -X POST http://localhost:8000/api/v1/rss/scrape -H "Authorization: Bearer <TOKEN>"

# 6) (İsteğe bağlı) Manuel planlama
curl -X POST http://localhost:8000/api/v1/rss/channels/1/schedule \
  -H "Authorization: Bearer <TOKEN>"
```

### 5.11 RSS ortam değişkenleri

`.env` dosyasında:

```env
RSS_ENABLED=true
RSS_SCRAPE_HOUR=6
RSS_REQUEST_TIMEOUT=30
RSS_MAX_ITEMS_PER_FEED=50
RSS_NEWS_MAX_AGE_DAYS=7
```

| Değişken | Açıklama |
|----------|----------|
| `RSS_SCRAPE_HOUR` | Günlük otomatik tarama saati (UTC) |
| `RSS_NEWS_MAX_AGE_DAYS` | Bu günden eski haberler pipeline'da seçilmez |
| `RSS_MAX_ITEMS_PER_FEED` | Her feed'den en fazla kaç haber çekilir |

---

## 6. Sosyal medya platformlarını bağlama

Her kanal birden fazla platforma bağlanabilir. Bağlantı bilgileri kanal bazında şifreli olarak saklanır.

**Endpoint:** `POST /api/v1/platforms/connect`

Desteklenen platformlar:

| `platform_type` | Açıklama |
|-----------------|----------|
| `instagram` | Instagram Reels |
| `youtube_shorts` | YouTube Shorts |
| `tiktok` | TikTok |

### 6.1 Instagram

```bash
curl -X POST http://localhost:8000/api/v1/platforms/connect \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "channel_id": 1,
    "platform_type": "instagram",
    "credentials_json": {
      "access_token": "META_ACCESS_TOKEN",
      "token_expires_at": "2026-12-31T23:59:59+00:00",
      "ig_user_id": "123456789",
      "auth_type": "facebook_login"
    },
    "platform_specific_settings": {
      "share_to_feed": true
    }
  }'
```

> Instagram Reels için videonun **herkese açık bir HTTP(S) URL** üzerinden erişilebilir olması gerekir. `.env` dosyasında `PUBLIC_MEDIA_BASE_URL` ayarlayın.

### 6.2 YouTube Shorts

```bash
curl -X POST http://localhost:8000/api/v1/platforms/connect \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "channel_id": 1,
    "platform_type": "youtube_shorts",
    "credentials_json": {
      "access_token": "YA_ACCESS_TOKEN",
      "refresh_token": "REFRESH_TOKEN",
      "token_expires_at": "2026-12-31T23:59:59+00:00",
      "client_id": "YOUTUBE_CLIENT_ID",
      "client_secret": "YOUTUBE_CLIENT_SECRET"
    }
  }'
```

### 6.3 TikTok

```bash
curl -X POST http://localhost:8000/api/v1/platforms/connect \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "channel_id": 1,
    "platform_type": "tiktok",
    "credentials_json": {
      "access_token": "TIKTOK_ACCESS_TOKEN",
      "refresh_token": "TIKTOK_REFRESH_TOKEN",
      "open_id": "TIKTOK_OPEN_ID",
      "token_expires_at": "2026-12-31T23:59:59+00:00"
    }
  }'
```

### 6.4 Platform durumunu sorgula

**Endpoint:** `GET /api/v1/platforms/status`

Tüm kanallar:

```bash
curl http://localhost:8000/api/v1/platforms/status \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

Belirli bir kanal:

```bash
curl "http://localhost:8000/api/v1/platforms/status?channel_id=1" \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

Olası durumlar: `connected`, `expired`, `error`

---

## 7. Video planlama (manuel akış)

Agent kullanmadan, kendi içeriğinizi planlayabilirsiniz. Bu akış video metadatasını oluşturur ve arka planda üretim görevini kuyruğa alır.

**Endpoint:** `POST /api/v1/videos/schedule`

| Alan | Zorunlu | Açıklama |
|------|---------|----------|
| `channel_id` | Evet | Hedef kanal ID |
| `hook_text` | Evet | Videonun dikkat çekici açılış metni |
| `caption` | Hayır | Yayın açıklaması |
| `generated_hashtags` | Hayır | Hashtag listesi |
| `scheduled_at` | Evet | Yayın zamanı (ISO 8601, UTC önerilir) |

```bash
curl -X POST http://localhost:8000/api/v1/videos/schedule \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "channel_id": 1,
    "hook_text": "Hayatımı değiştiren 3 para alışkanlığı",
    "caption": "Kaydet ve uygula!",
    "generated_hashtags": ["finans", "ipucu", "reels"],
    "scheduled_at": "2026-06-24T15:00:00+00:00"
  }'
```

**Ne olur?**

1. Video kaydı `pending` durumunda oluşturulur
2. `generate_video_content_task` Celery kuyruğuna eklenir
3. `scheduled_at` zamanı geldiğinde Celery beat `check_due_videos` görevi yayınlamayı tetikler

---

## 8. Agent (Pipeline) nasıl çalışır?

Agent, **LangGraph** ile tanımlanmış çok adımlı bir otomasyon akışıdır. Kanal ayarlarınızı ve geçmiş performansı kullanarak uçtan uca video üretir ve yayınlar.

### Akış diyagramı

```
Başlangıç
    │
    ▼
┌─────────────────────┐
│ memory_enrichment   │  ← Son yayınlanan videoları bağlama olarak yükler
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│ select_news         │  ← RSS yetkisi varsa kullanılmamış haber seçer
└─────────┬───────────┘
          │ (haber yoksa akış sonlanır)
          ▼
┌─────────────────────┐
│ generate_idea       │  ← LLM ile video fikri üretir (RSS haberine dayalı olabilir)
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│ validate_idea       │  ← Fikri puanlar (min skor: 7/10)
└─────────┬───────────┘
          │
    ┌─────┼─────┐
    │     │     │
  devam retry red
    │     │     └──► Son (fikir reddedildi)
    │     └──────────► generate_idea'ya geri dön (max 3 deneme)
    ▼
┌─────────────────────┐
│ generate_script     │  ← Senaryo ve seslendirme metni
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│ persist_metadata    │  ← Video kaydını veritabanına yazar
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│ produce_video       │  ← MoneyPrinterTurbo ile video üretir
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│ publish             │  ← Bağlı tüm platformlara yükler
└─────────┬───────────┘
          ▼
        Son
```

### Agent'ın kullandığı veriler

- **Kanal profili:** niş, hedef kitle, dil, ton, `system_prompt`, `base_hashtags`
- **Geçmiş performans:** Son 10 yayınlanan videonun hook ve hashtag bilgileri
- **RSS haber (varsa):** Kanala yetki verilmiş feed'lerden seçilen güncel haber; fikir bu habere dayandırılır
- **LLM:** Fikir ve senaryo üretimi (`LLM_PROVIDER`, `LLM_MODEL_NAME`)
- **MoneyPrinterTurbo:** 9:16 dikey video montajı

### RSS haber modunda agent davranışı

| Durum | Davranış |
|-------|----------|
| Kanalda RSS feed yetkisi **yok** | Eski davranış: serbest fikir üretimi |
| RSS yetkisi var, **kullanılmamış haber var** | Fikir zorunlu olarak seçilen habere dayandırılır |
| RSS yetkisi var, **haber yok** | Pipeline o çalıştırmada atlanır (video üretilmez) |

Her pipeline çalışması en fazla **1 haber** kullanır. 10 haber = 10 ayrı pipeline çalışması (RSS modunda `rss_interval_minutes` arayla planlanır).

### Fikir kalite kontrolü

- Minimum kabul skoru: **7** (`IDEA_MIN_SCORE`)
- Maksimum yeniden deneme: **3** (`IDEA_MAX_RETRIES`)
- Skor yetersizse agent yeni fikir üretir; 3 denemeden sonra akış sonlanır

### Pipeline JSON sözleşmesi

Agent, LLM çıktılarını ve kanal bağlamını `PipelineVideoContent` sözleşmesiyle taşır:

| Aşama | JSON modeli | Açıklama |
|-------|-------------|----------|
| `memory_enrichment` | `ChannelContext` | Kanal profili state'e yazılır |
| `select_news` | — | RSS feed yetkisi ve kullanılmamış haber seçimi |
| `generate_idea` | `VideoIdeaOutput` | Başlık, hook, anahtar kelimeler (30–50 sn) |
| `validate_idea` | `IdeaValidation` | Skor, kabul/red, kısa gerekçe |
| `generate_script` | `VideoScriptOutput` | Seslendirme metni ve hashtag'ler |
| `produce_video` | `GenerateVideoParams` | MPT'ye tam map (`video_language`, `voice_name`, `custom_system_prompt` dahil) |

`persist_metadata` aşamasında script hashtag'leri ile kanal `base_hashtags` birleştirilir (tekrarlar elenir).

### LLM token ayarları

`.env` dosyasında yapılandırılabilir:

| Değişken | Varsayılan | Açıklama |
|----------|------------|----------|
| `LLM_MAX_TOKENS` | `8192` | Fikir üretimi üst sınırı |
| `LLM_VALIDATION_MAX_TOKENS` | `1024` | Fikir doğrulama üst sınırı |
| `LLM_SCRIPT_MAX_TOKENS` | `8192` | Senaryo üretimi üst sınırı |
| `LLM_UNLIMITED_OUTPUT` | `false` | `true` ise Ollama'ya `max_tokens` gönderilmez |
| `MPT_VOICE_NAME_EN` | `en-US-AriaNeural` | İngilizce kanallar için MPT sesi |

LLM çağrıları structured output kullanır: Ollama'da `format` (JSON schema), bulut sağlayıcılarda `response_format: json_object`.

---

## 9. Agent'ı çalıştırma

Agent iki şekilde tetiklenebilir: **manuel** veya **otomatik (zamanlanmış)**.

### 9.1 Manuel tetikleme

**Endpoint:** `POST /api/v1/pipeline/trigger`

```bash
curl -X POST http://localhost:8000/api/v1/pipeline/trigger \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"channel_id": 1}'
```

**Yanıt (202 Accepted):**

```json
{
  "message": "Pipeline triggered for channel 1",
  "task_id": "celery-task-uuid"
}
```

Bu istek Celery worker'a görev gönderir; agent arka planda çalışır.

> **Ön koşullar:** Celery worker çalışıyor olmalı, LLM ve MoneyPrinterTurbo erişilebilir olmalı, kanala en az bir platform bağlı olmalıdır.

### 9.2 Otomatik tetikleme

Agent iki farklı zamanlama moduyla otomatik çalışabilir:

#### Sabit saat modu (`fixed_hours`)

Kanal oluştururken `scheduling_mode: "fixed_hours"` ve `posting_hours` tanımladıysanız, Celery beat her **60 saniyede** bir kontrol eder:

- Kanal `is_active: true` ise
- Mevcut saat/dakika `posting_hours` listesindeyse

→ Agent otomatik olarak tetiklenir (kanal başına 1 çalışma).

**Örnek:** `"posting_hours": ["12:00:00", "18:00:00"]` → Her gün 12:00 ve 18:00 UTC'de agent çalışır.

#### RSS haber modu (`rss_news`)

`scheduling_mode: "rss_news"` olan kanallar için:

1. Günde 1 kez RSS feed'ler taranır (`RSS_SCRAPE_HOUR`, varsayılan 06:00 UTC)
2. Tarama bitince sistem, kanalın kullanılmamış haber sayısını hesaplar
3. `min(haber sayısı, daily_video_count, rss_max_videos_per_day)` kadar pipeline planlanır
4. Pipeline'lar `rss_interval_minutes` arayla Celery kuyruğuna eklenir

**Örnek:** 10 kullanılmamış haber, `rss_interval_minutes: 30` → 10 video; ilki hemen, sonrakiler 30'ar dakika arayla (06:00, 06:30, 07:00 … 10:30 UTC).

Aynı gün otomatik tekrar planlama yapılmaz. Tekrar planlamak için:

```bash
curl -X POST "http://localhost:8000/api/v1/rss/channels/1/schedule?force=true" \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

### 9.3 Pipeline durumunu sorgulama

**Endpoint:** `GET /api/v1/pipeline/status/{thread_id}`

Thread ID formatı: `channel-{channel_id}-{YYYY-MM-DD}-{HH}`

Örnek: `channel-1-2026-06-23-14`

```bash
curl http://localhost:8000/api/v1/pipeline/status/channel-1-2026-06-23-14 \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

**Yanıt örneği:**

```json
{
  "current_step": "produce_video",
  "retry_count": 0,
  "errors": [],
  "publish_results": null
}
```

Olası `current_step` değerleri: `started`, `memory_enrichment`, `select_news`, `generate_idea`, `validate_idea`, `generate_script`, `persist_metadata`, `produce_video`, `publish`

---

## 10. Video durumunu takip etme

### 10.1 Yaklaşan videolar

**Endpoint:** `GET /api/v1/videos/upcoming`

```bash
curl http://localhost:8000/api/v1/videos/upcoming \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

### 10.2 Tek video durumu

**Endpoint:** `GET /api/v1/videos/{video_id}/status`

```bash
curl http://localhost:8000/api/v1/videos/42/status \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

**Yanıt örneği:**

```json
{
  "id": 42,
  "channel_id": 1,
  "hook_text": "Hayatımı değiştiren 3 para alışkanlığı",
  "generation_status": "completed",
  "scheduled_at": "2026-06-24T15:00:00+00:00",
  "publish_statuses": [
    {
      "id": 1,
      "platform_type": "instagram",
      "publish_status": "published",
      "platform_video_id": "17895695668004550",
      "error_log": null,
      "published_at": "2026-06-24T15:01:23+00:00"
    }
  ]
}
```

### Durum değerleri

**Üretim durumu (`generation_status`):**

| Değer | Anlam |
|-------|-------|
| `pending` | Üretim bekliyor |
| `processing` | Üretim devam ediyor |
| `completed` | Video hazır |
| `failed` | Üretim başarısız |

**Yayın durumu (`publish_status`):**

| Değer | Anlam |
|-------|-------|
| `scheduled` | Yayın zamanı bekleniyor |
| `uploading` | Platforma yükleniyor |
| `published` | Yayınlandı |
| `failed` | Yayın başarısız (`error_log` alanına bakın) |

---

## 11. Önerilen iş akışı

Aşağıdaki sırayı izlemeniz önerilir.

### Klasik kanal (sabit saat)

```
1. Servisi ve Celery worker/beat'i başlat
        │
        ▼
2. Hesap oluştur → Token al
        │
        ▼
3. Kanal oluştur (scheduling_mode: fixed_hours, posting_hours)
        │
        ▼
4. Platform(ları) bağla
        │
        ▼
5. Agent otomatik çalışır veya POST /pipeline/trigger ile manuel tetikle
```

### RSS haber kanalı (otomatik haber → video)

```
1. Servisi ve Celery worker/beat'i başlat
        │
        ▼
2. Hesap oluştur → Token al
        │
        ▼
3. Kanal oluştur (scheduling_mode: rss_news, rss_interval_minutes)
        │
        ▼
4. GET /rss/feeds → feed ID'lerini al
        │
        ▼
5. POST /rss/channels/{id}/feeds → kanala feed yetkisi ver
        │
        ▼
6. Platform(ları) bağla
        │
        ▼
7. POST /rss/scrape → haberleri tara (veya günlük otomatik taramayı bekle)
        │
        ▼
8. Pipeline'lar otomatik planlanır (veya POST /rss/channels/{id}/schedule)
        │
        ▼
9. Video ve pipeline durumunu izle
```

### Genel akış (her iki mod)

```
5a. Manuel video planla          VEYA          5b. Agent'ı tetikle
    POST /videos/schedule                        POST /pipeline/trigger
        │                                              │
        ▼                                              ▼
6. Video durumunu izle          GET /videos/{id}/status
        │
        ▼
7. (Agent için) Pipeline durumu   GET /pipeline/status/{thread_id}
```

### İki akış arasındaki fark

| | Manuel planlama | Agent (Pipeline) | RSS Agent |
|---|---|---|---|
| **Fikir/senaryo** | Siz yazarsınız | LLM üretir | LLM, RSS haberine dayalı üretir |
| **Zamanlama** | `scheduled_at` | `posting_hours` veya manuel | `rss_news` + haber sayısı |
| **Video üretimi** | Basit arka plan görevi | MoneyPrinterTurbo | MoneyPrinterTurbo |
| **Yayınlama** | `scheduled_at` gelince | Üretim bitince hemen | Üretim bitince hemen |

---

## 12. Gerekli harici servisler

`.env` dosyasında yapılandırılması gereken servisler:

### LLM (fikir ve senaryo üretimi)

Varsayılan: **Ollama** (yerel)

```env
LLM_PROVIDER=ollama
LLM_MODEL_NAME=gemma4:12b
LLM_API_BASE=http://localhost:11434
LLM_MAX_TOKENS=8192
LLM_VALIDATION_MAX_TOKENS=1024
LLM_SCRIPT_MAX_TOKENS=8192
LLM_UNLIMITED_OUTPUT=false
```

Bulut sağlayıcı kullanmak için:

```env
LLM_PROVIDER=openai
LLM_MODEL_NAME=gpt-4o
LLM_API_KEY=sk-...
LLM_API_BASE=https://api.openai.com/v1
```

### MoneyPrinterTurbo (video üretimi)

```env
MPT_BASE_URL=http://localhost:8080
MPT_VOICE_NAME_EN=en-US-AriaNeural
MPT_API_TOKEN=your-token   # gerekiyorsa
```

### Instagram için medya URL'si

```env
PUBLIC_MEDIA_BASE_URL=https://cdn.example.com
```

### Platform OAuth (uygulama düzeyi)

```env
YOUTUBE_CLIENT_ID=...
YOUTUBE_CLIENT_SECRET=...
TIKTOK_CLIENT_KEY=...
TIKTOK_CLIENT_SECRET=...
META_APP_ID=...
META_APP_SECRET=...
```

ntfy bildirimleri için [Bölüm 13](#13-pipeline-bildirimleri-ntfy).

### RSS haber taraması

```env
RSS_ENABLED=true
RSS_SCRAPE_HOUR=6
RSS_REQUEST_TIMEOUT=30
RSS_MAX_ITEMS_PER_FEED=50
RSS_NEWS_MAX_AGE_DAYS=7
```

---

## 13. Pipeline bildirimleri (ntfy)

Pipeline her tamamlandığında (başarı, kısmi başarı veya hata) [ntfy.sh](https://ntfy.sh) üzerinden mobil uygulamaya push bildirim gider. Ücretsiz kullanım için hesap gerekmez; topic adı gizli tutulmalıdır.

`.env` ayarları:

```env
NTFY_ENABLED=true
NTFY_BASE_URL=https://ntfy.sh
NTFY_TOPIC=reels-pipeline-rastgele-gizli-string
```

`NTFY_TOPIC` tahmin edilmesi zor bir string olmalıdır (topic = şifre gibi düşünün).

**Manuel test:**

```bash
curl -H "Title: Test" -d "ReelsAutomation test" \
  https://ntfy.sh/reels-pipeline-rastgele-gizli-string
```

**Mobil uygulama:**

1. [ntfy](https://ntfy.sh) uygulamasını kurun
2. **Add subscription**
3. Varsayılan sunucu (`ntfy.sh`) kalsın — custom server gerekmez
4. Topic: `.env` içindeki `NTFY_TOPIC` değeri

Bildirim içeriği örneği: kanal adı, video ID, dosya yolu, platform yayın sonuçları (YouTube OK / TikTok FAIL vb.).

| Durum | Bildirim etiketi |
|-------|------------------|
| Tam başarı (video + tüm platformlar) | `white_check_mark` |
| Kısmi başarı (ör. YouTube fail) | `warning` |
| Pipeline exception | `x` |

ntfy erişilemez olsa bile pipeline çalışmaya devam eder; sadece log'a uyarı yazılır.

---

## 14. Sık karşılaşılan sorunlar

| Sorun | Olası neden | Çözüm |
|-------|-------------|-------|
| `401 Unauthorized` | Token süresi dolmuş veya eksik | Yeniden giriş yapın |
| `403 Forbidden` | İzin yok | Free tier varsayılan izinleri kontrol edin |
| `409 Conflict` | E-posta zaten kayıtlı | Farklı e-posta kullanın veya giriş yapın |
| `422 Unprocessable` | Platform credential formatı hatalı | [Bölüm 6](#6-sosyal-medya-platformlarını-bağlama) şemasına uygun gönderin |
| Agent tetiklenmiyor | Celery worker çalışmıyor | Worker ve beat'i başlatın |
| Otomatik agent çalışmıyor (`fixed_hours`) | `posting_hours` boş veya kanal pasif | Kanal ayarlarını kontrol edin |
| RSS kanalında video üretilmiyor | Feed yetkisi yok veya kullanılmamış haber yok | `POST /rss/channels/{id}/feeds` ve `POST /rss/scrape` çalıştırın |
| RSS planlama tekrarlanmıyor | Aynı gün zaten planlandı | `POST /rss/channels/{id}/schedule?force=true` kullanın |
| `scheduled_videos: 0` | `scheduling_mode` rss_news değil veya haber yok | Kanal modunu ve `GET /rss/channels/{id}/news` çıktısını kontrol edin |
| Video `failed` | MoneyPrinterTurbo erişilemiyor | `MPT_BASE_URL` ve servis durumunu kontrol edin |
| Instagram yayın hatası | Video URL'si erişilemiyor | `PUBLIC_MEDIA_BASE_URL` ayarlayın |
| Pipeline `404` | Yanlış thread_id | Format: `channel-{id}-{tarih}-{saat}` |
| Fikir sürekli reddediliyor | LLM kalitesi düşük | Model değiştirin veya `system_prompt` iyileştirin |
| Bildirim gelmiyor | Topic yanlış veya `NTFY_ENABLED=false` | `.env`, `curl https://ntfy.sh/{topic}` testi |

---

## 15. Pipeline Recovery (Operations)

Bu bölüm, pipeline run'larının takibi, stale run kurtarma ve Docker/Celery sorunlarında manuel müdahale için kısa bir runbook'tur.

### Beat sağlığı

Celery Beat periyodik görevleri (RSS scrape, pipeline dispatch, stale retry) tetikler. Beat ölürse hiçbir otomatik iş çalışmaz.

```bash
make health
docker compose ps
docker logs --tail 50 reels_automation_celery_beat
```

Beat heartbeat Redis'te `reels:celery_beat:last_heartbeat` anahtarında tutulur. 10 dakikadan eskiyse ntfy uyarısı gider (`NTFY_ENABLED=true` ise).

### Pipeline run listesi

Son run'ları API üzerinden görüntüleyin:

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/pipeline/runs?channel_id=1&limit=20"
```

| `status` | Anlam |
|----------|-------|
| `pending` | Celery kuyruğunda, henüz başlamadı |
| `running` | Aktif pipeline |
| `completed` | Başarıyla bitti |
| `failed` | Hata ile durdu |
| `stale` | 30+ dk güncellenmedi (watchdog işaretledi) |

### Stale run otomatik kurtarma

Beat her 5 dakikada `retry_stale_pipelines` çalıştırır:

1. `running` ve 30+ dk güncellenmemiş run'lar → `stale`
2. `failed` / `stale` ve `retry_count < 5` → exponential backoff ile yeniden kuyruğa alınır
3. Max retry aşıldıysa → ntfy `Pipeline exhausted` uyarısı; manuel müdahale gerekir

### Manuel retry

Tek kanal için pipeline tetikleme:

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"channel_id": 1}' \
  http://localhost:8000/api/v1/pipeline/trigger
```

RSS telafi (günlük slot kaybı): scrape sonrası otomatik çalışır. Eksik tamamlanan run varsa ve kullanılmamış haber varsa telafi pipeline'ları kuyruğa alınır. `rss_last_scheduled_date` guard'ı yalnızca ilk günlük dispatch'i korur; telafi bunu etkilemez.

Zorla RSS yeniden planlama:

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/rss/channels/1/schedule?force=true"
```

### Docker recovery

Worker veya Beat çöktüyse:

```bash
docker compose restart reels_automation_celery_worker reels_automation_celery_beat
docker logs -f reels_automation_celery_worker --tail 50
```

Beat schedule dosyası kalıcı volume'da tutulur (`celery_beat_data`). Worker `pipeline` kuyruğunu dinlemelidir: `-Q celery,pipeline`.

Tüm stack'i yeniden başlatma:

```bash
docker compose down && docker compose up -d
```

---

## API özeti

| Method | Endpoint | Auth | Açıklama |
|--------|----------|------|----------|
| POST | `/api/v1/auth/register` | Hayır | Kayıt |
| POST | `/api/v1/auth/token` | Hayır | Giriş / token |
| GET | `/api/v1/users/me` | Bearer | Profil |
| POST | `/api/v1/channels/` | Bearer | Kanal oluştur |
| GET | `/api/v1/channels/` | Bearer | Kanalları listele |
| PUT | `/api/v1/channels/{id}` | Bearer | Kanal güncelle |
| DELETE | `/api/v1/channels/{id}` | Bearer | Kanal sil |
| POST | `/api/v1/platforms/connect` | Bearer | Platform bağla |
| GET | `/api/v1/platforms/status` | Bearer | Platform durumu |
| POST | `/api/v1/videos/schedule` | Bearer | Video planla |
| GET | `/api/v1/videos/upcoming` | Bearer | Yaklaşan videolar |
| GET | `/api/v1/videos/{id}/status` | Bearer | Video durumu |
| POST | `/api/v1/pipeline/trigger` | Bearer | Agent tetikle |
| GET | `/api/v1/pipeline/runs` | Bearer | Pipeline run listesi (`channel_id`, `limit`) |
| GET | `/api/v1/pipeline/status/{thread_id}` | Bearer | Agent durumu |
| GET | `/api/v1/rss/feeds` | Bearer | RSS feed listesi |
| POST | `/api/v1/rss/feeds` | Bearer | Yeni RSS feed ekle |
| POST | `/api/v1/rss/scrape` | Bearer | Haber taramasını başlat |
| GET | `/api/v1/rss/channels/{id}/feeds` | Bearer | Kanalın feed yetkileri |
| POST | `/api/v1/rss/channels/{id}/feeds` | Bearer | Kanala feed yetkisi ver |
| DELETE | `/api/v1/rss/channels/{id}/feeds/{feed_id}` | Bearer | Feed yetkisini kaldır |
| GET | `/api/v1/rss/channels/{id}/news` | Bearer | Kanal haberleri |
| POST | `/api/v1/rss/channels/{id}/schedule` | Bearer | RSS pipeline planla |

---

*Son güncelleme: Haziran 2026*
