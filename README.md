# Supervisor Agent

Kullanıcının doğal dil sorusunu analiz eden, hangi alt servise yönlendireceğine Gemini ile karar veren ve sonuçları tek bir Türkçe yanıt olarak sentezleyen multi-agent orkestrasyon sistemi.

---

## Mimari

```
┌─────────────────────────────────────────────────────┐
│                   Kullanıcı (Browser)               │
│              Next.js Chat UI  :3000                 │
└─────────────────────┬───────────────────────────────┘
                      │  SSE  /ask/stream
                      ▼
┌─────────────────────────────────────────────────────┐
│           Supervisor Agent  :8000  (bu proje)       │
│                                                     │
│  FastAPI  ──►  Gemini 2.5 Flash (function-calling) │
│                      │                              │
│          ┌───────────┼───────────┐                  │
│          ▼           ▼           ▼                  │
│    :8001            :8002       :8003               │
│  YouTube RAG     SQL Agent  Browser Agent           │
└─────────────────────────────────────────────────────┘
```

Supervisor, Gemini'nin **function-calling** özelliğini kullanır: model hangi aracı çağıracağına kendisi karar verir. Aynı soru birden fazla aracı gerektirebilir — supervisor her adımda tool sonuçlarını modele besler ve model "yeterli bilgiye sahibim" deyene kadar döngü devam eder.

---

## Alt Servisler

| Servis | Port | Ne Yapar |
|---|---|---|
| **YouTube RAG** | 8001 | Video transcript'ini Qdrant'a ingest eder, RAG ile soruları yanıtlar |
| **SQL Agent** | 8002 | Doğal dil sorusunu SQL'e çevirir, Neon PostgreSQL'i sorgular |
| **Browser Agent** | 8003 | Web'de gezinir, güncel bilgi arar, sayfa içeriği çeker |

Her servis bağımsız bir proje olarak kendi `docker-compose.yml`'siyle ayağa kalkar. Supervisor onlara `host.docker.internal` (veya `localhost`) üzerinden erişir.

---

## Stack

### Backend
| Katman | Teknoloji |
|---|---|
| Web framework | **FastAPI** 0.115 |
| ASGI server | **Uvicorn** |
| LLM | **Google Gemini 2.5 Flash** (function-calling) |
| Gemini SDK | `google-generativeai` 0.8 |
| HTTP client | **httpx** (alt servislere async istek) |
| Streaming | FastAPI `StreamingResponse` — Server-Sent Events (SSE) |
| Config | `python-dotenv` + `.env` |

### Frontend
| Katman | Teknoloji |
|---|---|
| Framework | **Next.js 15** (App Router) |
| Dil | TypeScript |
| Stil | **Tailwind CSS** v3 + `@tailwindcss/typography` |
| Markdown | `react-markdown` + `remark-gfm` |
| SSE client | `fetch` + `ReadableStream` (EventSource POST desteklemediği için) |

---

## SSE Event Protokolü

`POST /ask/stream` endpoint'i aşağıdaki event'leri sırayla yayınlar:

```
data: {"type": "thinking",    "message": "Sorunuz analiz ediliyor..."}
data: {"type": "tool_call",   "step": 1, "tool": "query_youtube_rag", "args": {...}}
data: {"type": "tool_result", "step": 1, "tool": "query_youtube_rag", "preview": "..."}
data: {"type": "thinking",    "message": "Tüm sonuçlar toplandı, Gemini yanıtı sentezliyor..."}
data: {"type": "tool_call",   "step": 2, "tool": "query_sql_agent",   "args": {...}}
data: {"type": "tool_result", "step": 2, "tool": "query_sql_agent",   "preview": "..."}
data: {"type": "thinking",    "message": "Yanıt yazılıyor..."}
data: {"type": "answer",      "content": "İşte sonuçlar:\n..."}
data: {"type": "done",        "trace": [...]}
```

Hata durumunda `{"type": "error", "message": "..."}` yayınlanır.

---

## Kurulum ve Çalıştırma

### Ön koşullar

- Python 3.11+
- Node.js 20+
- Çalışan alt servisler (youtube-rag :8001, sql-agent :8002, browser-agent :8003)

### 1. Backend

```bash
# Bağımlılıkları kur
pip install -r requirements.txt

# .env dosyasını düzenle (aşağıdaki Ortam Değişkenleri bölümüne bak)
cp .env.example .env

# Geliştirme modunda başlat
uvicorn main:app --reload --port 8000
```

### 2. Frontend

```bash
cd frontend

# Bağımlılıkları kur
npm install

# Backend URL'ini ayarla (varsayılan zaten localhost:8000)
# frontend/.env.local içinde NEXT_PUBLIC_BACKEND_URL=http://localhost:8000

# Geliştirme modunda başlat
npm run dev
```

UI → [http://localhost:3000](http://localhost:3000)  
API → [http://localhost:8000/docs](http://localhost:8000/docs)

### Docker ile çalıştırma

```bash
# Sadece supervisor container'ını başlat
# Alt servislerin host'ta ilgili portlarda çalışıyor olması gerekir
docker compose up supervisor
```

> **Linux notu:** `docker-compose.yml` içindeki `extra_hosts` satırını açman gerekir:
> ```yaml
> extra_hosts:
>   - "host.docker.internal:host-gateway"
> ```

---

## Ortam Değişkenleri

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `GEMINI_API_KEY` | — | Google AI Studio API anahtarı (**zorunlu**) |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Kullanılacak Gemini modeli |
| `YOUTUBE_RAG_URL` | `http://localhost:8001` | YouTube RAG servis URL'si |
| `SQL_AGENT_URL` | `http://localhost:8002` | SQL Agent servis URL'si |
| `BROWSER_AGENT_URL` | `http://localhost:8003` | Browser Agent servis URL'si |
| `SUBSERVICE_TIMEOUT` | `30` | Alt servis istek timeout'u (sn) |
| `BROWSER_AGENT_TIMEOUT` | `60` | Browser agent özel timeout'u (sn) |
| `MAX_AGENT_STEPS` | `5` | Tool-calling döngüsü maksimum adım sayısı |

---

## Proje Yapısı

```
supervisor-agent/
├── main.py              # FastAPI app, /ask ve /ask/stream endpoint'leri
├── config.py            # Ortam değişkenleri ve sabitler
├── tools.py             # Gemini tool şemaları + alt servis HTTP çağrıları
├── requirements.txt     # Python bağımlılıkları
├── docker-compose.yml   # Supervisor container tanımı
├── .env                 # Ortam değişkenleri (git'e ekleme)
└── frontend/
    ├── src/app/
    │   ├── page.tsx     # Chat UI — SSE streaming, tool card'ları, markdown render
    │   ├── layout.tsx   # Root layout
    │   └── globals.css  # Tailwind base + custom animasyonlar
    ├── next.config.ts   # Next.js config
    ├── tailwind.config.ts
    └── .env.local       # NEXT_PUBLIC_BACKEND_URL
```

---

## API Referansı

### `POST /ask`
Senkron endpoint. Tüm araç çağrıları tamamlanana kadar bekler, tek seferde yanıt döner.

```json
// Request
{ "question": "Veritabanındaki ürünleri listele" }

// Response
{
  "answer": "Veritabanında şu ürünler bulunmaktadır: ...",
  "trace": [
    { "tool": "query_sql_agent", "args": { "question": "..." }, "result": "..." }
  ]
}
```

### `POST /ask/stream`
SSE streaming endpoint. Her araç adımını gerçek zamanlı olarak yayınlar.

### `GET /health`
```json
{ "status": "ok" }
```
