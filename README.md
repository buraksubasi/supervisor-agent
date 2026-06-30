# Supervisor Agent

Kullanıcının doğal dil sorusunu LangGraph pipeline'ıyla analiz eden, hangi alt servislere yönlendireceğine Gemini ile karar veren, sonuçları sentezleyen ve her isteği SQLite'a kaydederek gerçek zamanlı bir observability dashboard'u üzerinden izleyen multi-agent orkestrasyon sistemi.

---

## Mimari

```
┌──────────────────────────────────────────────────────────────────┐
│                        Kullanıcı (Browser)                       │
│         Next.js  :3000                                           │
│    ┌─────────────┐   ┌──────────────────────────────────────┐   │
│    │  Chat UI    │   │  Observability Dashboard             │   │
│    │  /          │   │  /dashboard                          │   │
│    │  SSE stream │   │  Metric kart · Latency · Eval · Cost │   │
│    └──────┬──────┘   └──────────────────────┬───────────────┘   │
└───────────┼──────────────────────────────────┼──────────────────┘
            │ POST /ask/stream                 │ GET /api/*
            ▼                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│                  Supervisor Agent  :8000  (bu proje)             │
│                                                                  │
│   FastAPI  ──►  LangGraph Pipeline                              │
│                      │                                           │
│           classify_intent (Gemini)                               │
│                      │                                           │
│              run_agent  ◄──── retry / advance                   │
│                      │                                           │
│           grade_response (Gemini)                                │
│                      │                                           │
│               synthesize (Gemini)                                │
│                      │                                           │
│          ┌───────────┼───────────┐                               │
│          ▼           ▼           ▼                               │
│       :8001       :8002       :8003                              │
│   YouTube RAG  SQL Agent  Browser Agent                          │
│                                                                  │
│   SQLite (eval.db)  ◄──  Trace · ToolCall · Evaluation          │
│   LLM-as-Judge          Faithfulness · Relevance · Hallucination │
└──────────────────────────────────────────────────────────────────┘
```

---

## LangGraph Pipeline

Supervisor, Gemini'nin function-calling yerine **LangGraph** ile yönetilen açık bir state machine kullanır:

```
START
  └─► classify_intent   ← Gemini: hangi tool'lar, hangi argümanlarla?
          │
          ├─[unknown]─► handle_unknown ─► END
          │
          └─[tool(s)]─► run_agent      ← TOOL_DISPATCH ile alt servisi çağır
                              │
                         grade_response ← Gemini: cevap yeterli mi?
                              │
                  ┌───────────┼─────────────┐
                  │           │             │
               [retry]   [next_tool]   [sufficient]
                  │           │             │
              run_agent  advance_to    synthesize ─► END
                         next_tool
```

| Node | Görevi |
|---|---|
| `classify_intent` | Soruyu analiz eder, tool listesini ve argümanlarını planlar |
| `run_agent` | Seçili tool'u çağırır (YouTube / SQL / Browser) |
| `grade_response` | Tool cevabını sadece o tool'un görevi için değerlendirir (0-2 deneme) |
| `advance_to_next_tool` | Çoklu tool planında sıradaki tool'a geçer, `attempts` sıfırlar |
| `synthesize` | Tüm tool sonuçlarını Türkçe tek yanıtta birleştirir |

---

## Observability & Eval

Her istek otomatik olarak SQLite'a kaydedilir. Dashboard üzerinden gerçek zamanlı izlenir.

### Veritabanı Şeması

```
traces          ── trace_id, question, answer, agent_type, latency_ms,
                   input_tokens, output_tokens, cost_usd, status
    │
    ├── tool_calls   ── tool_name, tool_args, tool_result, step_order
    │
    └── evaluations  ── faithfulness, relevance, hallucination, overall_score
```

### LLM-as-Judge (`eval/judge.py`)

`POST /api/evaluate/{trace_id}` çağrıldığında Gemini üç ayrı prompt ile puanlar:

| Metrik | Aralık | İyi değer | Ne ölçer |
|---|---|---|---|
| `faithfulness` | 0–1 | 1.0 | Cevap kaynağa sadık mı? |
| `relevance` | 0–1 | 1.0 | Soruyu tam yanıtlıyor mu? |
| `hallucination` | 0–1 | 0.0 | Kaynakta olmayan bilgi var mı? |
| `overall` | 0–1 | 1.0 | `(f + r + (1−h)) / 3` |

### Token & Maliyet Takibi

Her Gemini çağrısından `usage_metadata` okunur, birikimli olarak state'e eklenir:

```
Maliyet = (input_tokens × $0.15 + output_tokens × $0.60) / 1_000_000
```

### Dashboard Sekmeleri (`/dashboard`)

| Sekme | İçerik |
|---|---|
| **Overview** | 4 metric kart (toplam istek, ort. latency, toplam maliyet, ort. eval skoru) + agent dağılımı + mini chart'lar |
| **Latency** | Agent tipine göre renk kodlu zaman serisi line chart (Recharts) |
| **Eval Skorları** | Faithfulness / Relevance / Hallucination bar chart + Overall trend |
| **Trace Explorer** | Filtrelenebilir trace tablosu; tıklayınca soru/cevap/tool detayları + inline değerlendirme butonu |
| **Maliyet** | Günlük input/output token bar chart + USD maliyet grafiği |

---

## Alt Servisler

| Servis | Port | Ne Yapar |
|---|---|---|
| **YouTube RAG** | 8001 | Video transcript'ini Qdrant'a ingest eder, RAG ile soruları yanıtlar |
| **SQL Agent** | 8002 | Doğal dil sorusunu SQL'e çevirir, Neon PostgreSQL'i sorgular |
| **Browser Agent** | 8003 | Web'de gezinir, güncel bilgi arar, sayfa içeriği çeker |

Her servis bağımsız bir proje olarak kendi `docker-compose.yml`'siyle ayağa kalkar. Supervisor onlara `host.docker.internal` üzerinden erişir.

---

## Stack

### Backend
| Katman | Teknoloji |
|---|---|
| Web framework | **FastAPI** 0.115 |
| ASGI server | **Uvicorn** |
| Agent pipeline | **LangGraph** 0.2 |
| LLM | **Google Gemini 2.5 Flash** |
| Gemini SDK | `google-generativeai` 0.8 |
| HTTP client | **httpx** (alt servislere async istek) |
| Streaming | FastAPI `StreamingResponse` — SSE |
| Veritabanı | **SQLite** (`eval.db`) + **SQLAlchemy** 2.0 async + **aiosqlite** |
| Eval | Gemini (LLM-as-judge) — faithfulness · relevance · hallucination |
| Config | `python-dotenv` + `.env` |

### Frontend
| Katman | Teknoloji |
|---|---|
| Framework | **Next.js 15** (App Router) |
| Dil | TypeScript |
| Stil | **Tailwind CSS** v3 + `@tailwindcss/typography` |
| Grafikler | **Recharts** (line · bar · composed chart) |
| Markdown | `react-markdown` + `remark-gfm` |
| SSE client | `fetch` + `ReadableStream` |

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
data: {"type": "done",        "trace": [...], "trace_id": "uuid"}
```

Hata durumunda `{"type": "error", "message": "..."}` yayınlanır.

---

## Kurulum ve Çalıştırma

### Ön koşullar

- Python 3.11+ · Node.js 20+
- Çalışan alt servisler (youtube-rag :8001, sql-agent :8002, browser-agent :8003)

### 1. Backend

```bash
# Sanal ortam oluştur ve aktif et
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux

# Bağımlılıkları kur
pip install -r requirements.txt

# .env dosyasını düzenle
cp .env.example .env

# Veritabanını başlat (ilk çalıştırmada lifespan hook otomatik yapar)
uvicorn main:app --reload --port 8000
```

### 2. Frontend

```bash
cd frontend

npm install

# frontend/.env.local
# NEXT_PUBLIC_BACKEND_URL=http://localhost:8000

npm run dev
```

| Adres | İçerik |
|---|---|
| http://localhost:3000 | Chat UI |
| http://localhost:3000/dashboard | Observability Dashboard |
| http://localhost:8000/docs | FastAPI Swagger |

### Docker ile çalıştırma

```bash
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
| `MAX_AGENT_STEPS` | `5` | LangGraph döngüsü maksimum adım sayısı |
| `DATABASE_URL` | `sqlite+aiosqlite:///./eval.db` | Trace & eval veritabanı |

---

## Proje Yapısı

```
supervisor-agent/
├── main.py                   # FastAPI app — /ask, /ask/stream, /api/* endpoint'leri
├── config.py                 # Ortam değişkenleri
├── tools.py                  # Alt servis HTTP çağrıları (youtube / sql / browser)
├── requirements.txt
├── docker-compose.yml
├── eval.db                   # SQLite — traces, tool_calls, evaluations
│
├── graph/                    # LangGraph pipeline
│   ├── builder.py            # StateGraph tanımı, node bağlantıları, routing
│   ├── nodes.py              # classify_intent · run_agent · grade_response · synthesize
│   └── state.py              # SupervisorState TypedDict
│
├── database/                 # Observability katmanı
│   ├── connection.py         # SQLAlchemy async engine, init_db
│   ├── models.py             # Trace · ToolCall · Evaluation ORM modelleri
│   └── repository.py        # CRUD + dashboard sorguları (latency/eval serisi)
│
├── eval/
│   └── judge.py              # LLM-as-judge: faithfulness · relevance · hallucination
│
└── frontend/
    ├── src/
    │   ├── app/
    │   │   ├── page.tsx          # Chat UI (SSE streaming, tool card'ları)
    │   │   ├── layout.tsx        # Root layout + NavBar
    │   │   ├── globals.css
    │   │   └── dashboard/
    │   │       └── page.tsx      # Dashboard (5 sekme)
    │   └── components/
    │       ├── NavBar.tsx
    │       └── dashboard/
    │           ├── StatCard.tsx
    │           ├── LatencyChart.tsx   # Recharts line chart
    │           ├── EvalChart.tsx      # Recharts bar + line composed
    │           ├── CostChart.tsx      # Token & USD bar chart
    │           ├── TraceTable.tsx     # Filtrelenebilir trace listesi
    │           └── TraceDetail.tsx    # Trace detayı + inline eval butonu
    ├── next.config.ts
    ├── tailwind.config.ts
    └── .env.local
```

---

## API Referansı

### `POST /ask`
Senkron endpoint. Tüm araç çağrıları tamamlanana kadar bekler.

```json
// Request
{ "question": "Veritabanındaki ürünleri listele" }

// Response
{
  "answer": "Veritabanında şu ürünler bulunmaktadır: ...",
  "trace": [{ "tool": "query_sql_agent", "args": {}, "result": "..." }],
  "trace_id": "uuid"
}
```

### `POST /ask/stream`
SSE streaming endpoint. Her araç adımını gerçek zamanlı olarak yayınlar.

### Dashboard Endpoint'leri

| Method | Path | Açıklama |
|---|---|---|
| `GET` | `/api/stats?days=7` | Özet metrikler (istek sayısı, latency, maliyet, eval skoru) |
| `GET` | `/api/traces?limit=50&agent_type=` | Trace listesi (`tools_used` dahil) |
| `GET` | `/api/traces/{id}` | Tek trace detayı (tool_calls + evaluation) |
| `GET` | `/api/latency-chart?days=7` | Agent'a göre günlük latency serisi |
| `GET` | `/api/eval-chart?days=7` | Günlük eval skor serisi |
| `POST` | `/api/evaluate/{id}` | Belirli trace için LLM-as-judge tetikle |
| `GET` | `/health` | `{"status": "ok"}` |
