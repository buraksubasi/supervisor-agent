"""
Supervisor Agent
================
Gelen kullanıcı sorusunu Gemini'nin function-calling özelliğiyle analiz eder,
hangi alt servis(ler)in çağrılması gerektiğine karar verir, onları tetikler
ve sonuçları sentezleyip kullanıcıya tek bir cevap olarak döner.

Çalıştırma (local, Docker olmadan):
    pip install -r requirements.txt
    uvicorn main:app --reload --port 8000

Çalıştırma (Docker Compose içinde):
    docker compose up supervisor
"""

import json
import logging
from graph.builder import supervisor_graph
import google.generativeai as genai
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from config import GEMINI_API_KEY, GEMINI_MODEL, MAX_AGENT_STEPS
from tools import TOOL_DEFINITIONS, TOOL_DISPATCH

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("supervisor")

genai.configure(api_key=GEMINI_API_KEY)

app = FastAPI(title="Supervisor Agent")

# Next.js'ten istek atabilmek için CORS — production'da origin'i daraltmayı unutma
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    answer: str
    trace: list[dict]  # hangi tool'ların hangi sırayla çağrıldığını gösterir (debug/UI için)


SYSTEM_INSTRUCTION = (
    "Sen, kullanıcının sorusuna göre doğru aracı seçip çağıran bir supervisor "
    "agent'sın. Elindeki araçlar: YouTube videoları hakkında soru cevaplayan bir "
    "RAG sistemi, bir veritabanına doğal dille soru sorduran bir SQL agent ve "
    "web'de gezinen bir browser agent. Kullanıcının sorusu birden fazla aracı "
    "gerektiriyorsa sırayla hepsini çağırabilirsin. Bir aracı çağırmadan önce "
    "gerekli tüm bilgiye (örn. video URL'si) sahip olduğundan emin ol; eksikse "
    "kullanıcıya doğrudan sor. Tüm araç sonuçlarını topladıktan sonra kullanıcıya "
    "net, Türkçe bir özet/cevap ver."
)


@app.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest):
    result = await supervisor_graph.ainvoke({
        "question": req.question,
        "selected_tool": "unknown",
        "tool_args": {},
        "agent_response": None,
        "is_sufficient": None,
        "attempts": 0,
        "trace": [],
        "final_answer": None,
    })
    
    return AskResponse(
        answer=result["final_answer"] or "",
        trace=result["trace"],
    )


@app.post("/ask/stream")
async def ask_stream(req: AskRequest):
    def emit(data: dict) -> str:
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    async def event_generator():
        try:
            yield emit({"type": "thinking", "message": "Sorunuz analiz ediliyor..."})

            initial_state = {
                "question": req.question,
                "selected_tool": "unknown",
                "tool_args": {},
                "agent_response": None,
                "is_sufficient": None,
                "attempts": 0,
                "trace": [],
                "final_answer": None,
            }

            collected_trace = []
            final_answer = ""

            async for event in supervisor_graph.astream_events(
                initial_state,
                version="v2",
            ):
                kind = event["event"]
                name = event.get("name", "")

                if kind == "on_chain_start":
                    if name == "classify_intent":
                        yield emit({"type": "thinking", "message": "Soru analiz ediliyor..."})
                    elif name == "run_agent":
                        state = event.get("data", {}).get("input", {})
                        tool = state.get("selected_tool", "")
                        tool_labels = {
                            "query_youtube_rag": "YouTube RAG",
                            "query_sql_agent": "SQL Agent",
                            "query_browser_agent": "Browser Agent",
                        }
                        yield emit({
                            "type": "thinking",
                            "message": f"{tool_labels.get(tool, tool)} çağrılıyor...",
                        })
                    elif name == "grade_response":
                        yield emit({"type": "thinking", "message": "Cevap kalitesi değerlendiriliyor..."})
                    elif name == "synthesize":
                        yield emit({"type": "thinking", "message": "Yanıt yazılıyor..."})

                elif kind == "on_chain_end":
                    if name == "classify_intent":
                        output = event.get("data", {}).get("output", {})
                        tool = output.get("selected_tool", "")
                        args = output.get("tool_args", {})
                        if tool != "unknown":
                            yield emit({"type": "tool_call", "step": 1, "tool": tool, "args": args})

                    elif name == "run_agent":
                        output = event.get("data", {}).get("output", {})
                        response = output.get("agent_response", "")
                        trace = output.get("trace", [])
                        collected_trace.extend(trace)
                        tool = trace[-1]["tool"] if trace else ""
                        yield emit({
                            "type": "tool_result",
                            "step": len(collected_trace),
                            "tool": tool,
                            "preview": response[:300] if response else "",
                        })

                    elif name == "grade_response":
                        output = event.get("data", {}).get("output", {})
                        if not output.get("is_sufficient", True):
                            yield emit({"type": "thinking", "message": "Cevap yetersiz, tekrar deneniyor..."})

                    elif name in ("synthesize", "handle_unknown"):
                        output = event.get("data", {}).get("output", {})
                        final_answer = output.get("final_answer", "")
                        if final_answer:
                            yield emit({"type": "answer", "content": final_answer})

            yield emit({"type": "done", "trace": collected_trace})

        except Exception as exc:
            logger.error("Stream hatası: %s", exc, exc_info=True)
            yield emit({"type": "error", "message": str(exc)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/health")
async def health():
    return {"status": "ok"}