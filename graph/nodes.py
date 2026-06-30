import json
import logging
import google.generativeai as genai
from config import GEMINI_API_KEY, GEMINI_MODEL
from tools import TOOL_DISPATCH
from graph.state import SupervisorState

genai.configure(api_key=GEMINI_API_KEY)
logger = logging.getLogger("supervisor")

# ── 1. classify_intent ──────────────────────────────────────────────────────

CLASSIFY_PROMPT = """Sen bir intent classifier'sın. Kullanıcının sorusunu analiz edip
hangi tool'u hangi argümanlarla çağıracağına karar ver.

Mevcut tool'lar:
- query_youtube_rag: YouTube video içeriği soruları. Args: video_url, question
- query_sql_agent: Veritabanı/istatistik soruları. Args: question  
- query_browser_agent: Web arama, güncel bilgi. Args: task
- unknown: Hiçbirine uymuyorsa

SADECE şu JSON formatında cevap ver:
{
  "tool": "query_youtube_rag" | "query_sql_agent" | "query_browser_agent" | "unknown",
  "args": { ... },
  "reason": "neden bu tool (1 cümle)"
}"""

CLASSIFY_PROMPT = """Sen bir intent classifier'sın. Kullanıcının sorusunu analiz edip
hangi tool'ları hangi sırayla çağıracağına karar ver.

Mevcut tool'lar:
- query_youtube_rag: YouTube video içeriği soruları. Args: video_url, question
- query_sql_agent: Veritabanı/istatistik soruları. Args: question
- query_browser_agent: Web arama, güncel bilgi. Args: task

Soru birden fazla tool gerektiriyorsa hepsini listele.

SADECE şu JSON formatında cevap ver, başka hiçbir şey yazma:
{{
  "tools": [
    {{"tool": "query_youtube_rag", "args": {{"video_url": "...", "question": "..."}}, "reason": "..."}},
    {{"tool": "query_sql_agent", "args": {{"question": "..."}}, "reason": "..."}}
  ]
}}

Eğer hiçbir tool uymuyorsa:
{{
  "tools": [{{"tool": "unknown", "args": {{}}, "reason": "..."}}]
}}"""

def _token_delta(response) -> tuple[int, int]:
    """Gemini response'undan (input, output) token sayısını çıkar."""
    meta = getattr(response, "usage_metadata", None)
    if meta is None:
        return 0, 0
    return (
        getattr(meta, "prompt_token_count", 0) or 0,
        getattr(meta, "candidates_token_count", 0) or 0,
    )


def classify_intent(state: SupervisorState) -> SupervisorState:
    model = genai.GenerativeModel(GEMINI_MODEL)
    response = model.generate_content(
        f"{CLASSIFY_PROMPT}\n\nKullanıcı sorusu: {state['question']}"
    )
    inp, out = _token_delta(response)

    try:
        clean = response.text.strip().replace("```json", "").replace("```", "").strip()
        data = json.loads(clean)
        planned = data.get("tools", [])

        valid_tools = ["query_youtube_rag", "query_sql_agent", "query_browser_agent"]
        planned = [
            t for t in planned
            if t.get("tool") in valid_tools + ["unknown"]
        ]

        if not planned:
            planned = [{"tool": "unknown", "args": {}, "reason": "Tanımlanamayan intent"}]

        first = planned[0]
        logger.info("[classify_intent] %d tool planlandı: %s", len(planned),
                    [t["tool"] for t in planned])

    except json.JSONDecodeError:
        logger.error("[classify_intent] JSON parse hatası: %s", response.text)
        planned = [{"tool": "unknown", "args": {}, "reason": "Parse hatası"}]
        first = planned[0]

    return {
        "planned_tools": planned,
        "current_tool_index": 0,
        "selected_tool": first["tool"],
        "tool_args": first.get("args", {}),
        "input_tokens": state.get("input_tokens", 0) + inp,
        "output_tokens": state.get("output_tokens", 0) + out,
    }


# ── 2. run_agent ─────────────────────────────────────────────────────────────
# Tek bir node tüm agent'ları handle eder — tool ismini state'ten alır

async def run_agent(state: SupervisorState) -> SupervisorState:
    tool_name = state["selected_tool"]
    tool_args = state["tool_args"]
    
    handler = TOOL_DISPATCH.get(tool_name)
    if handler is None:
        result = f"[bilinmeyen tool: {tool_name}]"
    else:
        logger.info("[run_agent] %s çağrılıyor | args: %s", tool_name, tool_args)
        result = await handler(**tool_args)
        logger.info("[run_agent] %s tamamlandı | sonuç (120 kar): %.120s", tool_name, result)
    
    all_responses = state.get("all_responses", [])
    all_responses = all_responses + [{"tool": tool_name, "result": result}]
    
    return {
        "agent_response": result,
        "all_responses": all_responses,
        "trace": state["trace"] + [{"tool": tool_name, "args": tool_args, "result": result}],
    }


# ── 3. grade_response ────────────────────────────────────────────────────────

GRADE_PROMPT = """Kullanıcı sorusuna verilen cevabı değerlendir.

Soru: {question}
Cevap: {answer}

Cevap şu kriterlerden herhangi birini karşılıyorsa YETERSİZ say:
- "ulaşılamadı", "hata", "bilinmiyor" gibi hata mesajları içeriyor
- Çok kısa (50 karakterden az) ve soruya cevap vermiyor
- "bilmiyorum" veya benzeri belirsiz ifadeler içeriyor

SADECE şu JSON formatında cevap ver:
{{
  "is_sufficient": true | false,
  "reason": "neden yeterli/yetersiz (1 cümle)"
}}"""

def grade_response(state: SupervisorState) -> SupervisorState:
    if state["attempts"] >= 2:
        logger.info("[grade_response] Max deneme aşıldı, kabul ediliyor.")
        return {"is_sufficient": True, "attempts": state["attempts"] + 1}

    # Grader'a tam soruyu değil, o anki tool'un spesifik görevini ver.
    # Böylece YouTube cevabı "SQL sorusu cevaplandı mı?" diye değil
    # yalnızca kendi görevi için değerlendirilir.
    tool_args = state.get("tool_args", {})
    specific_question = (
        tool_args.get("question")
        or tool_args.get("task")
        or state["question"]
    )

    model = genai.GenerativeModel(GEMINI_MODEL)
    prompt = GRADE_PROMPT.format(
        question=specific_question,
        answer=state["agent_response"] or "",
    )
    response = model.generate_content(prompt)
    
    inp, out = _token_delta(response)

    try:
        clean = response.text.strip().replace("```json", "").replace("```", "").strip()
        data = json.loads(clean)
        is_sufficient = data.get("is_sufficient", True)
        reason = data.get("reason", "")
        logger.info("[grade_response] Yeterli: %s | %s", is_sufficient, reason)
    except json.JSONDecodeError:
        is_sufficient = True

    return {
        "is_sufficient": is_sufficient,
        "attempts": state["attempts"] + 1,
        "input_tokens": state.get("input_tokens", 0) + inp,
        "output_tokens": state.get("output_tokens", 0) + out,
    }


# ── 4. synthesize ────────────────────────────────────────────────────────────
# Agent cevabını Türkçe, kullanıcı dostu formata çevir

def synthesize(state: SupervisorState) -> SupervisorState:
    model = genai.GenerativeModel(GEMINI_MODEL)
    
    # Tüm tool sonuçlarını birleştir
    all_responses = state.get("all_responses", [])
    
    if len(all_responses) == 1:
        context = f"Servis cevabı: {all_responses[0]['result']}"
    else:
        context = "\n\n".join([
            f"[{r['tool']}] sonucu:\n{r['result']}"
            for r in all_responses
        ])
    
    prompt = f"""Kullanıcının sorusuna birden fazla servis cevap verdi.
Tüm cevapları birleştirerek kullanıcıya Türkçe, net ve anlaşılır tek bir yanıt sun.

Soru: {state['question']}

{context}

Yanıt:"""
    
    response = model.generate_content(prompt)
    inp, out = _token_delta(response)
    return {
        "final_answer": response.text,
        "input_tokens": state.get("input_tokens", 0) + inp,
        "output_tokens": state.get("output_tokens", 0) + out,
    }


# ── 5. handle_unknown ────────────────────────────────────────────────────────

def handle_unknown(state: SupervisorState) -> SupervisorState:
    return {
        "final_answer": "Üzgünüm, bu soruyu hangi servise yönlendireceğimi anlayamadım. "
                       "YouTube videosu, veritabanı sorgusu veya web araması hakkında sorular sorabilirsiniz.",
    }