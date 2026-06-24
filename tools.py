"""
Bu dosya iki seyi tanimlar:
1) Gemini'ye gosterilecek tool semalari (LLM bunlardan hangisini cagiracagina karar verir)
2) Her tool cagrildiginda gercekten ne yapilacagi (ilgili alt servise HTTP istegi)

Gercek servis semalarina gore guncellendi:
- youtube-rag: /ingest (url -> video_id), /video/{video_id}/status, /query (video_id, question)
- sql-agent:   /api/chat/stream (question, session_id) -- streaming response
- browser-agent: /agent/run (task) -- senkron, websocket /agent/stream kullanilmadi
"""

import re
import httpx
from config import (
    YOUTUBE_RAG_URL,
    SQL_AGENT_URL,
    BROWSER_AGENT_URL,
    DEFAULT_TIMEOUT,
    BROWSER_AGENT_TIMEOUT,
)

# ---------------------------------------------------------------------------
# 1) Gemini function-calling semalari
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "function_declarations": [
            {
                "name": "query_youtube_rag",
                "description": (
                    "Bir YouTube videosu hakkinda soru sormak, video ozetletmek "
                    "veya video icerigiyle ilgili herhangi bir bilgi almak icin kullanilir. "
                    "Kullanici bir YouTube linki paylastiginda veya bir videodan bahsettiginde cagrilmali. "
                    "Video daha once islenmemisse otomatik olarak islenir (ingest), bu yuzden "
                    "her zaman gecerli bir video_url ile cagrilmali."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "video_url": {
                            "type": "string",
                            "description": "Ilgili YouTube video URL'si",
                        },
                        "question": {
                            "type": "string",
                            "description": "Video hakkinda sorulan soru veya 'ozetle' gibi bir istek",
                        },
                    },
                    "required": ["video_url", "question"],
                },
            },
            {
                "name": "query_sql_agent",
                "description": (
                    "Veritabanindaki verilerle ilgili dogal dilde sorulan sorular icin kullanilir. "
                    "Kullanici 'kac musteri var', 'son ayin satislari ne kadar' gibi veri sorgulari "
                    "sordugunda cagrilmali."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": "Veritabani hakkinda dogal dilde soru",
                        },
                    },
                    "required": ["question"],
                },
            },
            {
                "name": "query_browser_agent",
                "description": (
                    "Internette gezinme, bir web sitesinde islem yapma, guncel bilgi arama "
                    "veya bir web sayfasindan veri cekme gerektiren gorevler icin kullanilir."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task": {
                            "type": "string",
                            "description": "Browser agent'in gerceklestirmesi gereken gorev tanimi",
                        },
                    },
                    "required": ["task"],
                },
            },
        ]
    }
]


# ---------------------------------------------------------------------------
# 2) Alt servis cagrilari (gercek implementasyon)
# ---------------------------------------------------------------------------

_YOUTUBE_ID_PATTERN = re.compile(
    r"(?:youtu\.be/|youtube\.com/(?:watch\?v=|embed/|shorts/))([A-Za-z0-9_-]{11})"
)


def _extract_video_id(url: str):
    """YouTube URL'sinden 11 karakterlik video ID'sini cikarir.
    youtube-rag servisinin video_id'yi nasil urettigini biliyorsan
    (orn. baska bir hashleme kullaniyorsa) bu fonksiyonu ona gore guncelle.
    """
    match = _YOUTUBE_ID_PATTERN.search(url)
    return match.group(1) if match else None


async def call_youtube_rag(video_url: str, question: str) -> str:
    """YouTube RAG akisi: video_id cikar -> daha once ingest edilmis mi kontrol et
    -> edilmemisse ingest et -> soruyu sor.
    """
    video_id = _extract_video_id(video_url)
    if not video_id:
        return f"[gecersiz YouTube URL'si, video_id cikarilamadi: {video_url}]"

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        try:
            # 1) Video daha once islenmis mi kontrol et
            status_resp = await client.get(f"{YOUTUBE_RAG_URL}/video/{video_id}/status")
            status_resp.raise_for_status()
            exists = status_resp.json().get("exists", False)

            # 2) Islenmemisse ingest et
            if not exists:
                ingest_resp = await client.post(
                    f"{YOUTUBE_RAG_URL}/ingest", json={"url": video_url}
                )
                ingest_resp.raise_for_status()
                ingest_resp.json()  # ingest sonucu loglamak istersen burada kullan

            # 3) Soruyu sor
            query_resp = await client.post(
                f"{YOUTUBE_RAG_URL}/query",
                json={"question": question, "video_id": video_id},
            )
            query_resp.raise_for_status()
            data = query_resp.json()
            return data.get("answer", str(data))

        except httpx.HTTPError as e:
            return f"[youtube-rag servisine ulasilamadi: {e}]"


async def call_sql_agent(question: str, session_id: str = "supervisor_session") -> str:
    """SQL query agent servisine istek atar.

    Stream formati SSE: her satir "data: {json}" seklinde, JSON icindeki "type"
    alani su degerleri alabilir:
      - "thinking": ara adim/log (SQL agent'in hangi tool'u calistirdigi vs.)
      - "token"   : nihai cevabin bir parcasi (birlestirilince tam cevabi olusturur)
      - "done"    : stream bitti sinyali

    Biz sadece "token" icin gelen content'leri birlestirip nihai cevabi olusturuyoruz.
    """
    import json

    url = f"{SQL_AGENT_URL}/api/chat/stream"
    payload = {"question": question, "session_id": session_id}

    answer_parts = []
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            async with client.stream("POST", url, json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    raw = line[len("data:"):].strip()
                    if not raw:
                        continue
                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    event_type = event.get("type")
                    if event_type == "token":
                        answer_parts.append(event.get("content", ""))
                    elif event_type == "done":
                        break
                    # "thinking" event'lerini su an yok sayiyoruz

        final_answer = "".join(answer_parts).strip()
        return final_answer or "[sql-agent bos cevap dondu]"
    except httpx.HTTPError as e:
        return f"[sql-agent servisine ulasilamadi: {e}]"


async def call_browser_agent(task: str) -> str:
    """Browser agent (MCP tabanli) servisine istek atar.
    Bu servis genelde daha yavas calistigi icin ayri bir timeout kullaniliyor.
    Senkron /agent/run endpoint'i kullaniliyor (websocket /agent/stream degil).
    """
    url = f"{BROWSER_AGENT_URL}/agent/run"
    payload = {"task": task}

    async with httpx.AsyncClient(timeout=BROWSER_AGENT_TIMEOUT) as client:
        try:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            # run_agent'in tam olarak ne dondurdugune gore bu satiri guncellemen gerekebilir
            if isinstance(data, dict):
                return data.get("result") or data.get("answer") or str(data)
            return str(data)
        except httpx.HTTPError as e:
            return f"[browser-agent servisine ulasilamadi: {e}]"


# Tool ismi -> gercek fonksiyon eslemesi (main.py bunu kullanarak dispatch yapacak)
TOOL_DISPATCH = {
    "query_youtube_rag": call_youtube_rag,
    "query_sql_agent": call_sql_agent,
    "query_browser_agent": call_browser_agent,
}